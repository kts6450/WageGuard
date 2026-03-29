"""
사업주-노동자 이분 그래프 분석 모듈

핵심 기능:
1. 이분 그래프 구성 (사업주 ↔ 노동자)
2. 중심성 지표 계산 (Degree / Betweenness / PageRank)
3. 반복 착취 사업주 탐지
4. 착취 네트워크 커뮤니티 탐지
"""

import networkx as nx
import numpy as np
import pandas as pd
from collections import defaultdict


def build_bipartite_graph(df_raw: pd.DataFrame) -> nx.Graph:
    """
    사업주-노동자 이분 그래프 생성
    노드: 사업주(workplace), 노동자(worker)
    엣지: 고용 관계 (임금 지급 기록 기반)
    엣지 속성: 평균 지연일, 실지급 비율, 착취 여부
    """
    G = nx.Graph()

    for wid, group in df_raw.groupby("workplace_id"):
        is_exploited = group["is_exploited"].iloc[0]
        exploit_type = group["exploitation_type"].iloc[0]
        industry = group["industry"].iloc[0]
        region = group["region"].iloc[0]
        n_workers = group["n_workers"].iloc[0]

        G.add_node(
            f"W{wid:03d}",
            node_type="workplace",
            is_exploited=is_exploited,
            exploitation_type=exploit_type,
            industry=industry,
            region=region,
        )

        wage_ratio = (group["actual_wage"] / group["contracted_wage"]).mean()
        mean_delay = group["payment_delay_days"].mean()
        overtime_ratio = (
            group["actual_overtime_pay"] / (group["expected_overtime_pay"] + 1)
        ).mean()

        # 사업장 내 각 노동자를 개별 노드로 생성
        for worker_idx in range(n_workers):
            worker_id = f"P{wid:03d}_{worker_idx:02d}"
            G.add_node(worker_id, node_type="worker", workplace_id=wid)
            G.add_edge(
                f"W{wid:03d}",
                worker_id,
                wage_ratio=round(wage_ratio, 3),
                mean_delay=round(mean_delay, 1),
                overtime_ratio=round(overtime_ratio, 3),
                is_exploited=is_exploited,
            )

    return G


def compute_network_metrics(G: nx.Graph) -> pd.DataFrame:
    """
    네트워크 중심성 지표 계산
    사업장 노드에 대해서만 분석 (노동자 노드 제외)
    """
    workplace_nodes = [n for n, d in G.nodes(data=True) if d.get("node_type") == "workplace"]

    degree_centrality = nx.degree_centrality(G)
    betweenness = nx.betweenness_centrality(G, normalized=True)
    pagerank = nx.pagerank(G, alpha=0.85)

    records = []
    for node in workplace_nodes:
        wid = int(node[1:])
        data = G.nodes[node]
        neighbors = list(G.neighbors(node))
        edge_data = [G[node][nb] for nb in neighbors]

        records.append({
            "workplace_id": wid,
            "node_id": node,
            "industry": data.get("industry", ""),
            "region": data.get("region", ""),
            "is_exploited": data.get("is_exploited", 0),
            "exploitation_type": data.get("exploitation_type", "none"),
            "n_workers": len(neighbors),
            "degree_centrality": round(degree_centrality[node], 4),
            "betweenness_centrality": round(betweenness[node], 6),
            "pagerank": round(pagerank[node], 6),
            "mean_wage_ratio": round(np.mean([e.get("wage_ratio", 1) for e in edge_data]), 3),
            "mean_delay": round(np.mean([e.get("mean_delay", 0) for e in edge_data]), 1),
            "mean_overtime_ratio": round(np.mean([e.get("overtime_ratio", 1) for e in edge_data]), 3),
        })

    return pd.DataFrame(records)


def detect_repeat_exploiters(df_raw: pd.DataFrame, metrics_df: pd.DataFrame) -> pd.DataFrame:
    """
    반복 착취 사업주 패턴 탐지
    - 동일 지역·업종 내 이전 노동자 이직 패턴 분석
    - 착취 점수(composite score) 계산
    """
    region_industry_stats = (
        df_raw.groupby(["region", "industry"])
        .agg(
            avg_wage_ratio=("actual_wage", lambda x: (x / df_raw.loc[x.index, "contracted_wage"]).mean()),
            avg_delay=("payment_delay_days", "mean"),
        )
        .reset_index()
    )

    result = metrics_df.copy()

    # 복합 착취 점수: 낮은 임금 비율 + 높은 지연일 + 낮은 초과수당 비율
    result["exploitation_score"] = (
        (1 - result["mean_wage_ratio"].clip(0, 1)) * 0.4
        + (result["mean_delay"].clip(0, 30) / 30) * 0.35
        + (1 - result["mean_overtime_ratio"].clip(0, 1)) * 0.25
    ).round(4)

    # PageRank 기반 영향력 지수 (네트워크 내 위치)
    result["network_influence"] = (
        result["pagerank"] / result["pagerank"].max()
    ).round(4)

    # 최종 위험 지수 = 착취 점수 × 영향력
    result["composite_risk"] = (
        result["exploitation_score"] * 0.7 + result["network_influence"] * 0.3
    ).round(4)

    return result.sort_values("composite_risk", ascending=False).reset_index(drop=True)


def find_high_risk_clusters(G: nx.Graph, metrics_df: pd.DataFrame, top_n: int = 20) -> dict:
    """
    고위험 사업장 클러스터 탐지
    업종·지역별 착취 집중 구역 식별
    """
    high_risk_workplaces = metrics_df.head(top_n)["node_id"].tolist()
    subgraph = G.subgraph(high_risk_workplaces + [
        nb for node in high_risk_workplaces for nb in G.neighbors(node)
    ])

    clusters = defaultdict(list)
    for wid in metrics_df.head(top_n)["workplace_id"]:
        row = metrics_df[metrics_df["workplace_id"] == wid].iloc[0]
        key = f"{row['region']}_{row['industry']}"
        clusters[key].append(wid)

    return {
        "subgraph": subgraph,
        "clusters": dict(clusters),
        "n_high_risk": len(high_risk_workplaces),
        "top_region_industry": max(clusters, key=lambda k: len(clusters[k])),
    }


def get_graph_summary(G: nx.Graph, metrics_df: pd.DataFrame) -> dict:
    """네트워크 전체 통계 요약"""
    workplace_nodes = [n for n, d in G.nodes(data=True) if d.get("node_type") == "workplace"]
    worker_nodes = [n for n, d in G.nodes(data=True) if d.get("node_type") == "worker"]

    exploited = metrics_df[metrics_df["is_exploited"] == 1]

    return {
        "total_workplaces": len(workplace_nodes),
        "total_workers": len(worker_nodes),
        "total_edges": G.number_of_edges(),
        "n_exploited": len(exploited),
        "exploitation_rate": round(len(exploited) / len(workplace_nodes) * 100, 1),
        "avg_workers_per_workplace": round(len(worker_nodes) / len(workplace_nodes), 1),
        "network_density": round(nx.density(G), 6),
        "avg_degree": round(np.mean([d for _, d in G.degree()]), 2),
        "top_exploited_industry": exploited["industry"].value_counts().index[0] if len(exploited) > 0 else "N/A",
        "top_exploited_region": exploited["region"].value_counts().index[0] if len(exploited) > 0 else "N/A",
    }


if __name__ == "__main__":
    import sys, os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from utils.data_generator import generate_payment_records

    print("데이터 생성 중...")
    df_raw = generate_payment_records(n_workplaces=500, exploitation_ratio=0.2, seed=42)

    print("이분 그래프 구성 중...")
    G = build_bipartite_graph(df_raw)

    print("중심성 지표 계산 중...")
    metrics_df = compute_network_metrics(G)

    print("반복 착취 탐지 중...")
    risk_df = detect_repeat_exploiters(df_raw, metrics_df)

    print("클러스터 탐지 중...")
    clusters = find_high_risk_clusters(G, risk_df)

    summary = get_graph_summary(G, metrics_df)

    print("\n" + "=" * 50)
    print("네트워크 분석 요약")
    print("=" * 50)
    for k, v in summary.items():
        print(f"  {k:<30}: {v}")

    print("\n상위 10개 고위험 사업장 (복합 위험 지수 기준):")
    display_cols = ["workplace_id", "industry", "region", "composite_risk", "exploitation_score", "n_workers", "is_exploited"]
    print(risk_df[display_cols].head(10).to_string(index=False))

    print(f"\n고위험 클러스터 집중 지역: {clusters['top_region_industry']}")
    print(f"클러스터 수: {len(clusters['clusters'])}")

    risk_df.to_csv("data/processed/network_risk_scores.csv", index=False)
    print("\n저장 완료: data/processed/network_risk_scores.csv")
