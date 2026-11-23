import streamlit as st
import akshare as ak
import pandas as pd

INDEX_CODE   = "000922"
LOOKBACK_YRS = 10
WEIGHTS      = {"dy": 0.35, "spread": 0.30, "pb": 0.20, "pe": 0.15}

st.set_page_config(page_title="红利雷达", page_icon="📊", layout="centered")

@st.cache_data(ttl=3600)
def fetch_valuation():
    df = ak.stock_zh_index_value_csindex(symbol=INDEX_CODE)
    df = df.rename(columns={"日期": "date", "市盈率": "pe",
                            "市净率": "pb", "股息率": "dy"})
    df["date"] = pd.to_datetime(df["date"])
    df["dy"] = pd.to_numeric(df["dy"].astype(str).str.replace("%", ""), errors="coerce")
    return df.sort_values("date").dropna(subset=["pe", "pb", "dy"])

@st.cache_data(ttl=3600)
def fetch_bond():
    b = ak.bond_zh_us_rate()
    b["date"] = pd.to_datetime(b["日期"])
    col = [c for c in b.columns if "中国国债收益率10年" in c][0]
    s = b.set_index("date")[col].dropna().astype(float)
    return s.sort_index()

def spread_to_score(spread):
    pts = [(1.0,0),(1.5,2.0),(2.0,4.0),(2.5,5.5),(3.0,7.0),(3.5,8.5),(4.0,10)]
    if spread <= pts[0][0]:  return pts[0][1]
    if spread >= pts[-1][0]: return pts[-1][1]
    for (x1,y1),(x2,y2) in zip(pts, pts[1:]):
        if x1 <= spread <= x2:
            return y1 + (y2-y1)*(spread-x1)/(x2-x1)

def score_at(df, i, bond):
    row = df.iloc[i]
    cutoff = row["date"] - pd.DateOffset(years=LOOKBACK_YRS)
    win = df[(df["date"] >= cutoff) & (df["date"] <= row["date"])]
    if len(win) < 100: return None
    dy_pct = (win["dy"] < row["dy"]).mean(); dy_s = dy_pct * 10
    pe_pct = (win["pe"] < row["pe"]).mean(); pe_s = (1-pe_pct) * 10
    pb_pct = (win["pb"] < row["pb"]).mean(); pb_s = (1-pb_pct) * 10
    b = bond.asof(row["date"]); spread = row["dy"] - b
    sp_s = spread_to_score(spread)
    total = dy_s*WEIGHTS["dy"] + sp_s*WEIGHTS["spread"] + pb_s*WEIGHTS["pb"] + pe_s*WEIGHTS["pe"]
    if row["dy"] < 3 or spread < 1: total = min(total, 6)
    return dict(date=row["date"], total=round(total,2), dy=row["dy"], dy_pct=dy_pct, dy_s=dy_s,
                spread=spread, sp_s=sp_s, pb=row["pb"], pb_pct=pb_pct, pb_s=pb_s,
                pe=row["pe"], pe_pct=pe_pct, pe_s=pe_s)

@st.cache_data(ttl=3600)
def calc_history():
    df = fetch_valuation(); bond = fetch_bond()
    m = df.set_index("date").resample("ME").last().dropna().reset_index()
    out = []
    for i in range(len(m)):
        r = score_at(m, i, bond)
        if r: out.append(r)
    return pd.DataFrame(out)

st.title("📊 中证红利估值雷达")
with st.spinner("首次加载约需 30–60 秒，请稍候…"):
    try:
        hist = calc_history()
        cur = hist.iloc[-1]
        bond_now = fetch_bond().asof(cur["date"])

        t = cur["total"]
        color = "#2e7d32" if t >= 6 else "#f57c00" if t >= 4 else "#c62828"
        label = ("共振低估 · 重点买入" if t >= 8 else "偏低估 · 正常定投" if t >= 6
                 else "中性 · 持有观察" if t >= 4 else "偏高估 · 减少定投" if t >= 2
                 else "共振高估 · 等待")

        st.markdown(
            f"<div style='text-align:center;padding:20px 0'>"
            f"<div style='font-size:64px;font-weight:800;color:{color};line-height:1'>{t:.1f}</div>"
            f"<div style='font-size:14px;color:#888'>/ 10 分</div>"
            f"<div style='font-size:18px;color:{color};margin-top:10px'>{label}</div>"
            f"<div style='font-size:12px;color:#999;margin-top:6px'>"
            f"数据日期 {cur['date'].strftime('%Y-%m-%d')} · 国债 {bond_now:.2f}%</div>"
            f"</div>", unsafe_allow_html=True)

        st.subheader("四维拆解")
        c1, c2 = st.columns(2)
        with c1:
            st.metric("股息率", f"{cur['dy']:.2f}%", f"分位 {cur['dy_pct']*100:.0f}%")
            st.progress(min(cur["dy_s"]/10,1.0)); st.caption(f"得分 {cur['dy_s']:.1f}")
            st.metric("PB", f"{cur['pb']:.2f}", f"分位 {cur['pb_pct']*100:.0f}%")
            st.progress(min(cur["pb_s"]/10,1.0)); st.caption(f"得分 {cur['pb_s']:.1f}")
        with c2:
            st.metric("股债利差", f"{cur['spread']:.2f}%", "股息率 − 国债")
            st.progress(min(cur["sp_s"]/10,1.0)); st.caption(f"得分 {cur['sp_s']:.1f}")
            st.metric("PE", f"{cur['pe']:.2f}", f"分位 {cur['pe_pct']*100:.0f}%")
            st.progress(min(cur["pe_s"]/10,1.0)); st.caption(f"得分 {cur['pe_s']:.1f}")

        st.subheader("历史分数走势")
        st.line_chart(hist.set_index("date")["total"], height=220)
    except Exception as e:
        st.error(f"数据获取失败：{e}")
        st.caption("可能是数据源临时异常，下拉刷新重试。")
