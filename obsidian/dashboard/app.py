"""
OBSIDIAN MM - Streamlit Dashboard

Diagnostic UI for market microstructure analysis.
NOT a trading frontend. NOT a signal generator.
"""

import asyncio
import json
import sys
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import yaml
from datetime import date, timedelta

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Page config - must be first Streamlit command
st.set_page_config(
    page_title="OBSIDIAN MM",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Data directory
DATA_DIR = PROJECT_ROOT / "data" / "processed" / "regimes"
BASELINES_DIR = PROJECT_ROOT / "data" / "baselines"
CONFIG_DIR = PROJECT_ROOT / "config"


def check_baseline_exists(ticker: str) -> dict | None:
    """Check if baseline exists for ticker and return basic info."""
    baseline_file = BASELINES_DIR / f"{ticker}.json"
    if baseline_file.exists():
        try:
            with open(baseline_file) as f:
                data = json.load(f)
                return {
                    "exists": True,
                    "baseline_date": data.get("baseline_date"),
                    "lookback_days": data.get("lookback_days"),
                }
        except Exception:
            return None
    return None


@st.cache_data
def load_ticker_list() -> list[str]:
    """Load ticker list from sources.yaml config."""
    sources_file = CONFIG_DIR / "sources.yaml"
    if sources_file.exists():
        with open(sources_file) as f:
            config = yaml.safe_load(f)
            return config.get("default_tickers", ["SPY", "QQQ", "IWM"])
    return ["SPY", "QQQ", "IWM"]


def load_real_data(ticker: str, selected_date: date) -> dict | None:
    """
    Load real pipeline results from processed data directory.

    Returns None if data not found.
    """
    data_file = DATA_DIR / ticker / f"{selected_date.isoformat()}.parquet"

    if not data_file.exists():
        return None

    try:
        df = pd.read_parquet(data_file)
        if df.empty:
            return None

        # Parse the stored data
        row = df.iloc[0]

        # Handle nested JSON fields
        regime_data = row.get("regime", {})
        if isinstance(regime_data, str):
            regime_data = json.loads(regime_data)

        unusualness_data = row.get("unusualness", {})
        if isinstance(unusualness_data, str):
            unusualness_data = json.loads(unusualness_data)

        features_data = row.get("features", {})
        if isinstance(features_data, str):
            features_data = json.loads(features_data)

        # Extract normalized features for display
        normalized = features_data.get("normalized", {})

        return {
            "ticker": ticker,
            "date": selected_date.isoformat(),
            "unusualness": {
                "score": unusualness_data.get("score", 0),
                "level": unusualness_data.get("level", "Unknown"),
                "raw_score": unusualness_data.get("raw_score", 0),
                "top_drivers": unusualness_data.get("top_drivers", []),
            },
            "regime": {
                "label": regime_data.get("regime", "Unknown"),
                "confidence": regime_data.get("confidence", 0),
                "explanation": regime_data.get("explanation", "No data"),
            },
            "features": {
                # All normalized features (z-scores and percentiles)
                **{k: v for k, v in normalized.items()},
                # Raw values (with _raw suffix to avoid conflicts)
                "dark_pool_ratio_raw": features_data.get("dark_pool_ratio", 0),
                "price_change_pct": features_data.get("price_change_pct", 0),
                "gex_raw": features_data.get("gex", 0),
                "dex_raw": features_data.get("dex", 0),
                "block_trade_count_raw": features_data.get("block_trade_count", 0),
                "iv_skew_raw": features_data.get("iv_skew", 0),
                "dark_pool_volume": features_data.get("dark_pool_volume", 0),
                "volume": features_data.get("volume", 0),
            },
        }

    except Exception as e:
        st.error(f"Error loading data: {e}")
        return None


def run_pipeline_sync(ticker: str, trade_date: date) -> dict | None:
    """Run the pipeline synchronously and return results."""
    try:
        from obsidian.pipeline.daily import DailyPipeline

        pipeline = DailyPipeline()
        result = asyncio.run(pipeline.run(ticker, trade_date))

        # Save result
        pipeline.save_result(result)

        # Convert to display format
        return {
            "ticker": ticker,
            "date": trade_date.isoformat(),
            "unusualness": {
                "score": result.unusualness.score,
                "level": result.unusualness.level.value,
                "raw_score": result.unusualness.raw_score,
                "top_drivers": [
                    {
                        "feature": d.feature,
                        "zscore": d.zscore,
                        "direction": d.direction,
                        "contribution_pct": d.contribution_pct,
                    }
                    for d in result.unusualness.top_drivers
                ],
            },
            "regime": {
                "label": result.regime.label.value,
                "confidence": result.regime.confidence,
                "explanation": result.regime.explanation,
            },
            "features": {
                "gex_zscore": result.features.normalized.get("gex_zscore", 0),
                "dex_zscore": result.features.normalized.get("dex_zscore", 0),
                "dark_pool_ratio_raw": result.features.dark_pool_ratio or 0,
                "block_trade_count_zscore": result.features.normalized.get("block_trade_count_zscore", 0),
                "price_change_pct": result.features.price_change_pct or 0,
                "iv_skew_zscore": result.features.normalized.get("iv_skew_zscore", 0),
            },
        }

    except Exception as e:
        st.error(f"Pipeline error: {e}")
        return None


def render_score_gauge(score: float) -> go.Figure:
    """Render unusualness score as a gauge."""
    if score < 40:
        color = "green"
    elif score < 70:
        color = "orange"
    else:
        color = "red"

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=score,
            title={"text": "Unusualness Score", "font": {"size": 16}},
            gauge={
                "axis": {"range": [0, 100], "tickwidth": 1},
                "bar": {"color": color},
                "steps": [
                    {"range": [0, 40], "color": "rgba(0, 128, 0, 0.2)"},
                    {"range": [40, 70], "color": "rgba(255, 165, 0, 0.2)"},
                    {"range": [70, 100], "color": "rgba(255, 0, 0, 0.2)"},
                ],
                "threshold": {
                    "line": {"color": "black", "width": 2},
                    "value": score,
                },
            },
        )
    )

    fig.update_layout(height=250, margin=dict(l=20, r=20, t=50, b=20))
    return fig


def render_regime_badge(label: str, confidence: float) -> None:
    """Render regime label as a styled badge."""
    colors = {
        "Gamma+ Control": "#4CAF50",
        "Gamma- Liquidity Vacuum": "#f44336",
        "Dark-Dominant Accumulation": "#9C27B0",
        "Absorption-like": "#2196F3",
        "Distribution-like": "#FF9800",
        "Neutral / Mixed": "#9E9E9E",
    }

    color = colors.get(label, "#9E9E9E")

    st.markdown(
        f"""
        <div style="
            background-color: {color};
            color: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
            margin: 10px 0;
        ">
            <h2 style="margin: 0; font-size: 1.5em;">{label}</h2>
            <p style="margin: 5px 0 0 0;">Confidence: {confidence:.0%}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_feature_bars(features: dict) -> go.Figure:
    """Render feature z-scores and percentiles as horizontal bars."""
    # Collect z-score features
    zscore_features = {
        k.replace("_zscore", "").replace("_", " ").title(): (v if v is not None else 0)
        for k, v in features.items()
        if k.endswith("_zscore")
    }

    # Collect percentile features (convert 0-100 to z-score-like -3 to +3 scale)
    # 50th percentile = 0, 2.5th = -2, 97.5th = +2
    pct_features = {}
    for k, v in features.items():
        if k.endswith("_pct") and k != "price_change_pct":
            if v is not None:
                # Convert percentile to pseudo z-score: (pct - 50) / 25
                # 0% -> -2, 50% -> 0, 100% -> +2
                pseudo_z = (v - 50) / 25
                name = k.replace("_pct", "").replace("_", " ").title()
                pct_features[f"{name} (pct)"] = pseudo_z

    all_features = {**zscore_features, **pct_features}

    if not all_features:
        return go.Figure()

    names = list(all_features.keys())
    values = list(all_features.values())
    colors = ["#f44336" if v < 0 else "#4CAF50" for v in values]

    fig = go.Figure(
        go.Bar(
            x=values,
            y=names,
            orientation="h",
            marker_color=colors,
            text=[f"{v:+.2f}σ" for v in values],
            textposition="outside",
        )
    )

    fig.update_layout(
        title="Feature Z-Scores",
        xaxis_title="Z-Score",
        yaxis_title="",
        height=300,
        margin=dict(l=20, r=20, t=40, b=20),
        xaxis=dict(range=[-3, 3]),
    )

    fig.add_vline(x=0, line_dash="solid", line_color="gray")
    fig.add_vline(x=-1.5, line_dash="dash", line_color="red", opacity=0.5)
    fig.add_vline(x=1.5, line_dash="dash", line_color="red", opacity=0.5)

    return fig


def render_no_data_state(ticker: str, selected_date: date) -> None:
    """Render the no-data state with run button."""
    st.warning(f"No data found for **{ticker}** on **{selected_date}**")

    st.markdown("""
    ### Options:

    1. **Run Pipeline Now** - Fetch data from APIs and compute diagnostics
    2. **Select Different Date** - Check if data exists for another date
    """)

    col1, col2 = st.columns([1, 2])

    with col1:
        if st.button("🚀 Run Pipeline", type="primary", use_container_width=True):
            with st.spinner(f"Fetching data for {ticker}..."):
                data = run_pipeline_sync(ticker, selected_date)
                if data:
                    st.success("Pipeline completed!")
                    st.session_state["data"] = data
                    st.rerun()
                else:
                    st.error("Pipeline failed. Check your API keys in .env")

    with col2:
        # Show available dates for this ticker
        ticker_dir = DATA_DIR / ticker
        if ticker_dir.exists():
            available = sorted([f.stem for f in ticker_dir.glob("*.parquet")])
            if available:
                st.info(f"Available dates for {ticker}: {', '.join(available[-5:])}")


def render_data_display(data: dict, baseline_info: dict | None = None) -> None:
    """Render the main data display."""
    # Top row: Score + Regime + Context
    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        st.plotly_chart(
            render_score_gauge(data["unusualness"]["score"]),
            use_container_width=True,
        )

    with col2:
        render_regime_badge(
            data["regime"]["label"],
            data["regime"]["confidence"],
        )

    with col3:
        dark_pool_pct = data['features'].get('dark_pool_ratio_raw')
        st.metric(
            "Dark Pool %",
            f"{dark_pool_pct:.1f}%" if dark_pool_pct is not None else "N/A",
        )
        # Show raw GEX if z-score is 0
        gex_zscore = data['features'].get('gex_zscore', 0) or 0
        if abs(gex_zscore) > 0.01:
            st.metric("GEX Z-Score", f"{gex_zscore:+.2f}")
        else:
            gex_raw = data['features'].get('gex_raw', 0) or 0
            st.metric("GEX (raw)", f"{gex_raw:,.0f}")
        price_change = data['features'].get('price_change_pct')
        st.metric(
            "Price Change",
            f"{price_change:+.2f}%" if price_change is not None else "N/A",
        )

    # Explanation section
    st.subheader("📝 Explanation")
    st.info(data["regime"]["explanation"])

    # Check if we have meaningful z-scores or percentiles
    zscore_values = [v for k, v in data["features"].items() if k.endswith("_zscore") and v is not None]
    # Percentiles: meaningful if they deviate from 50 (median)
    pct_values = [v for k, v in data["features"].items() if k.endswith("_pct") and k != "price_change_pct" and v is not None]
    has_meaningful_zscores = any(abs(v) > 0.01 for v in zscore_values) or any(abs(v - 50) > 5 for v in pct_values)

    if not has_meaningful_zscores:
        if baseline_info and baseline_info.get("exists"):
            # Baseline exists - z-scores near 0 means data is near baseline mean
            st.info(
                f"ℹ️ Z-scores are near zero, indicating metrics are close to baseline mean. "
                f"Baseline computed on {baseline_info.get('baseline_date', 'unknown')} "
                f"({baseline_info.get('lookback_days', 63)} day lookback)."
            )
        else:
            # No baseline - need to compute one
            st.warning(
                "⚠️ No baseline found for this ticker. Z-scores cannot be computed accurately. "
                "Run `python scripts/compute_baseline.py <TICKER>` to establish baseline."
            )

    # Two columns: Drivers + Features
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🎯 Top Score Drivers")
        if has_meaningful_zscores:
            for driver in data["unusualness"]["top_drivers"]:
                direction = "↑" if driver.get("direction") == "elevated" else "↓"
                contribution = driver.get("contribution_pct", 0) or 0
                if isinstance(contribution, float):
                    contribution = int(contribution)
                zscore = driver.get('zscore', 0) or 0
                st.progress(
                    min(contribution / 100, 1.0),
                    text=f"{direction} {driver.get('feature', 'unknown')}: {zscore:+.1f}σ ({contribution}%)",
                )
        else:
            if baseline_info and baseline_info.get("exists"):
                st.caption("All metrics are near baseline mean - nothing unusual detected.")
            else:
                st.caption("Compute baseline first to see meaningful drivers.")

    with col2:
        # Always show z-score chart
        st.plotly_chart(
            render_feature_bars(data["features"]),
            use_container_width=True,
        )

    # Show raw values section (always visible for reference)
    with st.expander("📊 Raw Feature Values", expanded=not has_meaningful_zscores):
        raw_col1, raw_col2, raw_col3 = st.columns(3)
        with raw_col1:
            dp_pct = data['features'].get('dark_pool_ratio_raw')
            st.metric("Dark Pool %", f"{dp_pct:.1f}%" if dp_pct is not None else "N/A")
            dp_vol = data['features'].get('dark_pool_volume') or 0
            st.metric("Dark Pool Vol", f"{dp_vol:,.0f}")
        with raw_col2:
            gex = data['features'].get('gex_raw') or 0
            st.metric("GEX", f"{gex:,.0f}")
            dex = data['features'].get('dex_raw') or 0
            st.metric("DEX", f"{dex:,.0f}")
        with raw_col3:
            blocks = data['features'].get('block_trade_count_raw') or 0
            st.metric("Block Trades", f"{blocks:.0f}")
            vol = data['features'].get('volume') or 0
            st.metric("Volume", f"{vol:,.0f}")


def main():
    """Main dashboard application."""
    # Sidebar
    with st.sidebar:
        st.title("🔮 OBSIDIAN MM")
        st.caption("Market-Maker Diagnostic Platform")

        st.divider()

        # Load tickers from config
        all_tickers = load_ticker_list()

        # Ticker selection
        ticker_mode = st.radio(
            "Ticker selection",
            ["Config list", "Custom"],
            horizontal=True,
            label_visibility="collapsed",
        )

        if ticker_mode == "Config list":
            ticker = st.selectbox(
                "Ticker",
                options=all_tickers,
                index=0,
            )
        else:
            ticker = st.text_input(
                "Enter ticker",
                value="SPY",
                max_chars=10,
                placeholder="e.g. AMD",
            ).upper().strip()

            if not ticker:
                ticker = "SPY"

        st.caption(f"{len(all_tickers)} tickers in config")

        # Date selection
        selected_date = st.date_input(
            "Date",
            value=date.today(),
            max_value=date.today(),
        )

        # Check baseline status for selected ticker
        baseline_status = check_baseline_exists(ticker)
        if baseline_status and baseline_status.get("exists"):
            st.success(f"✅ Baseline: {baseline_status.get('baseline_date', 'available')}")
        else:
            st.error("❌ No baseline")

        st.divider()

        # Refresh button
        if st.button("🔄 Refresh Data", use_container_width=True):
            st.session_state.pop("data", None)
            st.rerun()

        st.divider()

        # Disclaimer
        st.warning(
            "⚠️ **Diagnostic Only**\n\n"
            "This tool does NOT generate trading signals. "
            "It describes current market state, not predictions."
        )

        st.caption("No signals. No predictions. Just diagnostics.")

    # Main content
    st.title(f"📊 {ticker} - Market Microstructure Diagnostic")
    st.caption(f"Date: {selected_date}")

    # Try to load real data
    data = load_real_data(ticker, selected_date)
    baseline_info = check_baseline_exists(ticker)

    if data:
        if baseline_info and baseline_info.get("exists"):
            st.success(f"✅ Real data loaded | Baseline: {baseline_info.get('baseline_date', 'available')}")
        else:
            st.success("✅ Real data loaded from pipeline")
        render_data_display(data, baseline_info)
    else:
        render_no_data_state(ticker, selected_date)

    # Footer
    st.divider()
    st.caption(
        "OBSIDIAN MM - Observational Behavioral System for Institutional & "
        "Dealer-Informed Anomaly Networks | Diagnostic purposes only | "
        "Not financial advice"
    )


if __name__ == "__main__":
    main()
