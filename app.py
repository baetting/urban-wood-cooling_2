# -*- coding: utf-8 -*-
"""충남대 열섬 완화 시뮬레이터 (Streamlit) - 발표용
탈리그닌 목재 스펀지 / 우드칩 LID 기법 vs 일반 살수차
"""
import base64
import io
from pathlib import Path

import requests
import plotly.graph_objects as go
import streamlit as st
from PIL import Image

st.set_page_config(page_title="충남대 열섬 완화 시뮬레이터", page_icon="🌳", layout="wide")

# ──────────────────────────────────────────────
# 1. 이미지 탐색 (assets 폴더 → app.py 같은 폴더, 대소문자/확장자 무시)
# ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
SEARCH_DIRS = [BASE_DIR / "assets", BASE_DIR]
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def list_images():
    found = []
    for d in SEARCH_DIRS:
        if d.is_dir():
            for p in d.iterdir():
                if p.is_file() and p.suffix.lower() in IMG_EXT:
                    found.append(p)
    return found


def find_map(images):
    for p in images:
        if p.stem.lower().startswith("library_map"):
            return p
    return None


def find_background(images):
    others = [p for p in images if not p.stem.lower().startswith("library_map")]
    for p in others:
        if p.stem.lower().startswith("background"):
            return p
    if others:
        return max(others, key=lambda p: p.stat().st_mtime)
    return None


@st.cache_data(show_spinner=False)
def bg_to_base64(path_str, mtime):
    img = Image.open(path_str).convert("RGB")
    img.thumbnail((1600, 1600))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


IMAGES = list_images()
MAP_PATH = find_map(IMAGES)
BG_PATH = find_background(IMAGES)

# ──────────────────────────────────────────────
# 2. 소재별 상수 (※ 모두 시뮬레이션용 가정값)
# ──────────────────────────────────────────────
# ※ 근거 수준: [문헌] 논문·공공자료 인용 / [추정] 문헌값으로 계산 / [가정] 근거 미확보(발표 시 가정이라고 밝힐 것)
THICK_M = 0.05          # [가정] 시공 두께 5 cm
EVAP_RATE = 1.5         # [가정] 한낮 증발 속도 L/m²·h (저류수가 이 속도로 증발한다고 가정)
CARBON_FRAC = 0.47      # [문헌] 목재 탄소 함량 약 43~50% (Minnesota Stormwater Manual 표)

_chip_bulk, _chip_whc = 293, 0.585     # [문헌] 우드칩 용적밀도 0.293 g/cm³, 보수율 58.5%(건중량 대비)
_sp_bulk, _sp_uptake = 100, 2.24       # 스펀지 밀도 100 kg/m³ [가정], 흡수배율 최대 2.24 g/g [문헌]
_bc_bulk, _bc_whc, _bc_c = 250, 1.0, 0.80  # 바이오차: 용적밀도 0.15~0.33 g/cm³ 범위 내 0.25 [문헌 범위], 보수율 50.6~179.4%(건중량) 중 보수적으로 100% [문헌 범위], 탄소함량 80% [가정; 600℃ 목재 바이오차 92% 보고]
EVAP_DROP = 6.4         # [문헌] 증발냉각(물청소) 도로면 온도 저하 6.4℃ → 젖은 스펀지의 순간 냉각도 이 수준으로 가정

MATERIALS = {
    "우드칩": dict(
        cost=15000,                                   # [가정] 단가
        drop=2.5,                                     # [가정] 직접 실측 문헌 없음
        water=THICK_M * _chip_bulk * _chip_whc,       # [추정] 두께×용적밀도×보수율 ≈ 8.6 L/m²
        carbon=THICK_M * _chip_bulk * CARBON_FRAC,    # [추정] 소재에 저장된 탄소 ≈ 6.9 kg C/m²
        dust=1, color="#8D6E63"),
    "탈리그닌 스펀지": dict(
        cost=120000,                                  # [가정] 단가
        drop=EVAP_DROP,                               # [가정] 증발냉각 원리상 살수 효과(6.4℃) 수준
        water=THICK_M * _sp_bulk * _sp_uptake,        # [추정] ≈ 11.2 L/m²
        carbon=THICK_M * _sp_bulk * CARBON_FRAC,      # [추정] ≈ 2.4 kg C/m²
        dust=2, color="#2E7D32"),
    "목재 바이오차": dict(
        cost=40000,                                   # [가정] 단가
        drop=3.5,                                     # [가정] 검은색이라 일사 흡수↑ 가능성, 증발냉각은 우드칩보다 큼
        water=THICK_M * _bc_bulk * _bc_whc,           # [추정] ≈ 12.5 L/m²
        carbon=THICK_M * _bc_bulk * _bc_c,            # [추정] ≈ 10 kg C/m² (탄화로 안정화된 탄소)
        dust=2, color="#455A64"),
}
for _m in MATERIALS.values():
    _m["hours"] = _m["water"] / EVAP_RATE             # [추정] 냉각 지속시간(h) = 저류량 / 증발속도

# 비교 대조군: 일반 살수차
TRUCK = dict(
    cost_per_run=300,   # [가정] 1회 운영비 원/m² (인건비·연료 포함, 근거 미확보)
    drop=6.4,           # [문헌] 서울보건환경연구원: 물청소 후 도로면 온도 평균 6.4℃ 저하
    water_use=0.1,      # [추정] 1km당 약 1t 살포, 폭 10m 가정 → 0.1 L/m² (1회)
    hours=0.75,         # [문헌] 효과 30~60분 지속 → 중간값
    color="#1E88E5")
MAT_OPEX_PER_DAY = 0    # [가정] 목재 소재의 일 운영비(원/m²). 빗물로 재충전한다고 가정
DUST_LABEL = {0: "해당 없음", 1: "낮음", 2: "보통", 3: "높음"}

# ──────────────────────────────────────────────
# 3. 계산 함수 (화면 수식 expander와 동일한 식)
# ──────────────────────────────────────────────

def calc(material, applied_m2, total_m2, base_temp, window_h=10, scale=1.0):
    m = MATERIALS[material]
    applied_m2 = min(applied_m2, total_m2)
    ratio = applied_m2 / total_m2 if total_m2 > 0 else 0.0
    temp = base_temp - m["drop"] * ratio * scale
    budget = m["cost"] * applied_m2
    storage_l = m["water"] * applied_m2
    carbon_kg = m["carbon"] * applied_m2
    # 먼지 억제: 소재 등급 × 적용비율 → 4단계
    score = m["dust"] * ratio
    if ratio == 0:
        dust = 0
    elif score < 0.5:
        dust = 1
    elif score < 1.2:
        dust = 2
    else:
        dust = 3
    hours_eff = min(m["hours"], window_h) if ratio > 0 else 0
    return dict(ratio=ratio, applied=applied_m2, temp=temp, drop=base_temp - temp,
                cum=(base_temp - temp) * hours_eff, water_day=storage_l,
                opex_day=MAT_OPEX_PER_DAY * applied_m2,
                budget=budget, storage_l=storage_l, hours=m["hours"] if ratio > 0 else 0,
                carbon=carbon_kg, dust=dust)


def calc_truck(applied_m2, total_m2, base_temp, runs=3, window_h=10, scale=1.0):
    applied_m2 = min(applied_m2, total_m2)
    ratio = applied_m2 / total_m2 if total_m2 > 0 else 0.0
    return dict(ratio=ratio, temp=base_temp - TRUCK["drop"] * ratio * scale,
                drop=TRUCK["drop"] * ratio * scale, cost=TRUCK["cost_per_run"] * applied_m2,
                water_l=TRUCK["water_use"] * applied_m2, hours=TRUCK["hours"] if ratio > 0 else 0,
                runs=runs,
                cum=TRUCK["drop"] * ratio * scale * (min(runs * TRUCK["hours"], window_h) if ratio > 0 else 0),
                water_day=TRUCK["water_use"] * applied_m2 * runs,
                opex_day=TRUCK["cost_per_run"] * applied_m2 * runs)


# ──────────────────────────────────────────────
# 3-2. 실시간 기상(Open-Meteo, API 키 불필요) + GIS 지도 영역 계산
# ──────────────────────────────────────────────
CNU_LAT, CNU_LON = 36.3685, 127.3445   # 충남대 중앙도서관 부근(대략값, 사이드바에서 수정 가능)
SOLAR_K = 0.022      # [가정] 포장면 온도 = 기온 + 0.022 × 일사량(W/m²) → 일사 900W/m²이면 기온+약 20℃
SOLAR_REF = 700.0    # [가정] 일사량이 이 값(W/m²) 이상이면 냉각 효과 100%, 이하면 비례해서 감소


@st.cache_data(ttl=600, show_spinner=False)
def fetch_weather(lat, lon):
    """현재 + 오늘 시간대별 기온·일사량 (10분 캐시). 실패하면 None."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = dict(latitude=lat, longitude=lon, timezone="Asia/Seoul", forecast_days=1,
                  current="temperature_2m,relative_humidity_2m,shortwave_radiation,wind_speed_10m,apparent_temperature",
                  hourly="temperature_2m,shortwave_radiation")
    try:
        j = requests.get(url, params=params, timeout=8).json()
        cur = j["current"]
        hourly = dict(time=[t[-5:] for t in j["hourly"]["time"]],
                      air=j["hourly"]["temperature_2m"], rad=j["hourly"]["shortwave_radiation"])
        return dict(time=cur["time"].replace("T", " "), air=cur["temperature_2m"],
                    hum=cur["relative_humidity_2m"], rad=cur["shortwave_radiation"],
                    wind=cur["wind_speed_10m"], feel=cur["apparent_temperature"], hourly=hourly)
    except Exception:
        return None


def est_surface(air, rad):
    return air + SOLAR_K * rad


def polygon_area_m2(coords, lat0):
    """[(lon, lat), ...] 폴리곤 면적(m²). 작은 영역용 지역 평면 근사 + 신발끈 공식."""
    import math
    kx = 111320.0 * math.cos(math.radians(lat0))
    ky = 110574.0
    pts = [(lo * kx, la * ky) for lo, la in coords]
    a = 0.0
    for i in range(len(pts)):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % len(pts)]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2.0


def gis_map_area(lat, lon, ver):
    """실제 위성지도에 폴리곤/사각형을 그리면 면적(m²)을 돌려준다."""
    try:
        import folium
        from folium.plugins import Draw
        from streamlit_folium import st_folium
    except ImportError:
        st.error("folium / streamlit-folium 패키지가 필요합니다. requirements.txt를 확인하세요.")
        return 0.0
    m = folium.Map(location=[lat, lon], zoom_start=18, max_zoom=19, tiles=None, control_scale=True)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery", name="위성 지도", max_zoom=19).add_to(m)
    folium.TileLayer("OpenStreetMap", name="일반 지도", max_zoom=19).add_to(m)
    Draw(export=False,
         draw_options=dict(polygon=dict(shapeOptions=dict(color="red")),
                           rectangle=dict(shapeOptions=dict(color="red")),
                           polyline=False, circle=False, marker=False, circlemarker=False),
         edit_options=dict(edit=True, remove=True)).add_to(m)
    folium.LayerControl().add_to(m)
    out = st_folium(m, height=560, use_container_width=True, key=f"gis_{ver}",
                    returned_objects=["all_drawings"])
    total = 0.0
    for f in (out or {}).get("all_drawings") or []:
        g = f.get("geometry", {})
        if g.get("type") == "Polygon":
            total += polygon_area_m2(g["coordinates"][0], lat)
    return total



@st.cache_data(ttl=86400, show_spinner=False)
def fetch_summer_stats(lat, lon, n_years):
    """최근 n_years년 여름(6~8월) 일별 기온 → 연도별·월별 통계. 실패하면 None. (Open-Meteo Archive API)"""
    import datetime as dt
    today = dt.date.today()
    end_year = today.year if today.month >= 9 else today.year - 1
    start_year = end_year - n_years + 1
    try:
        j = requests.get("https://archive-api.open-meteo.com/v1/archive", params=dict(
            latitude=lat, longitude=lon, timezone="Asia/Seoul",
            start_date=f"{start_year}-06-01", end_date=f"{end_year}-08-31",
            daily="temperature_2m_max,temperature_2m_min,temperature_2m_mean",
            hourly="shortwave_radiation"), timeout=40).json()
        d = j["daily"]
        hh = j.get("hourly", {})
    except Exception:
        return None
    rows = []
    for t, hi, lo, me in zip(d["time"], d["temperature_2m_max"], d["temperature_2m_min"], d["temperature_2m_mean"]):
        if hi is None or lo is None or me is None:
            continue
        y, m = int(t[:4]), int(t[5:7])
        if m in (6, 7, 8):
            rows.append((y, m, hi, lo, me))
    if not rows:
        return None
    rad_vals = []
    for t_, v_ in zip(hh.get("time", []), hh.get("shortwave_radiation", [])):
        if v_ is not None and int(t_[5:7]) in (6, 7, 8) and 12 <= int(t_[11:13]) <= 15:
            rad_vals.append(v_)
    noon_rad = sum(rad_vals) / len(rad_vals) if rad_vals else 650.0   # 12~15시 평균 일사량(W/m²)

    def summarize(sel):
        n = len(sel)
        return dict(days=n,
                    avg_max=sum(r[2] for r in sel) / n, avg_min=sum(r[3] for r in sel) / n,
                    avg_mean=sum(r[4] for r in sel) / n,
                    abs_max=max(r[2] for r in sel), abs_min=min(r[3] for r in sel),
                    heat=sum(1 for r in sel if r[2] >= 33), tropical=sum(1 for r in sel if r[3] >= 25))
    years = sorted({r[0] for r in rows})
    return dict(start=start_year, end=end_year, noon_rad=noon_rad,
                total=summarize(rows),
                by_year={y: summarize([r for r in rows if r[0] == y]) for y in years},
                by_month={m: summarize([r for r in rows if r[1] == m]) for m in (6, 7, 8)})


def render_summer(lat, lon):
    """여름철 평균 최고·최저 기온 패널"""
    n_years = st.select_slider("분석 기간 (최근 N년 여름)", options=[3, 5, 10], value=5, key="summer_years")
    with st.spinner("여름철 기온 데이터를 불러오는 중..."):
        res = fetch_summer_stats(lat, lon, n_years)
    if not res:
        st.error("여름철 기온 데이터를 불러오지 못했습니다. 인터넷 연결을 확인하고 다시 시도하세요.")
        return
    tot = res["total"]
    st.caption(f"{res['start']}~{res['end']}년 6~8월 일별 기온 {tot['days']}일 기준 · 자료: Open-Meteo Archive(ERA5 재분석) · 위치 {lat:.4f}, {lon:.4f}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("평균 최고기온", f"{tot['avg_max']:.1f} ℃")
    c2.metric("평균 최저기온", f"{tot['avg_min']:.1f} ℃")
    c3.metric("기간 중 최고 / 최저", f"{tot['abs_max']:.1f} / {tot['abs_min']:.1f} ℃")
    c4.metric("연평균 폭염일 / 열대야", f"{tot['heat']/len(res['by_year']):.1f} / {tot['tropical']/len(res['by_year']):.1f} 일")
    st.success(f"☀️ 여름 평균 한낮 조건 → 평균 최고기온 {tot['avg_max']:.1f}℃ + 0.022 × 한낮 일사량 {res['noon_rad']:.0f} W/m² "
               f"= **포장면 추정 {tot['avg_max'] + SOLAR_K * res['noon_rad']:.1f} ℃** (사이드바 '여름 평균 한낮' 모드의 기준 온도)")
    years = list(res["by_year"].keys())
    fy = go.Figure()
    fy.add_trace(go.Bar(x=[str(y) for y in years], y=[res["by_year"][y]["avg_max"] for y in years],
                        name="평균 최고기온", marker_color="#E53935"))
    fy.add_trace(go.Bar(x=[str(y) for y in years], y=[res["by_year"][y]["avg_min"] for y in years],
                        name="평균 최저기온", marker_color="#1E88E5"))
    fy.update_layout(barmode="group", title="연도별 여름(6~8월) 평균 최고·최저기온 (℃)", height=340,
                     margin=dict(t=50, b=10))
    st.plotly_chart(fy, width="stretch")
    names = {6: "6월", 7: "7월", 8: "8월"}
    st.markdown("**월별 평균**")
    st.table({"월": [names[m] for m in (6, 7, 8)],
              "평균 최고(℃)": [f"{res['by_month'][m]['avg_max']:.1f}" for m in (6, 7, 8)],
              "평균 최저(℃)": [f"{res['by_month'][m]['avg_min']:.1f}" for m in (6, 7, 8)],
              "최고 기록(℃)": [f"{res['by_month'][m]['abs_max']:.1f}" for m in (6, 7, 8)],
              "폭염일(33℃↑)/전체기간": [f"{res['by_month'][m]['heat']}" for m in (6, 7, 8)],
              "열대야(최저25℃↑)/전체기간": [f"{res['by_month'][m]['tropical']}" for m in (6, 7, 8)]})
    st.caption("※ 재분석 격자(약 10km) 기온이라 기상청 대전 관측소 값과 1~2℃ 차이가 날 수 있고, 폭염일·열대야는 기상청 정의(최고 33℃↑, 최저 25℃↑)를 일별 값에 적용한 것입니다. 포장면 온도가 아니라 기온입니다.")


def inject_css():
    """시뮬레이터 화면 공통 스타일 (라이트/다크 테마 모두 대응)"""
    st.markdown("""<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css');
html, body, .stApp, button, input, textarea { font-family: 'Pretendard', 'Malgun Gothic', sans-serif; }
.block-container { padding-top: 1.6rem; max-width: 1400px; }
.hero { background: linear-gradient(120deg, #1B5E20 0%, #2E7D32 45%, #0277BD 100%); border-radius: 18px;
        padding: 22px 28px; margin-bottom: 10px; box-shadow: 0 4px 16px rgba(0,0,0,.15); }
.hero-t { font-size: 1.9rem; font-weight: 800; color: #fff; line-height: 1.3; }
.hero-s { font-size: 1rem; color: rgba(255,255,255,.88); margin-top: 4px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; margin: 6px 0 12px; }
.chip { background: rgba(128,128,128,.12); border: 1px solid rgba(128,128,128,.28); border-radius: 999px;
        padding: 6px 14px; font-weight: 600; font-size: .92rem; }
.chip.good { background: rgba(46,125,50,.16); border-color: rgba(46,125,50,.55); color: #2E7D32; }
[data-testid="stMetric"] { background: rgba(128,128,128,.07); border: 1px solid rgba(128,128,128,.22);
        border-radius: 14px; padding: 12px 16px; }
[data-testid="stMetricValue"] { font-weight: 800; }
[data-testid="stMetricLabel"] p { font-weight: 600; opacity: .8; }
button[data-baseweb="tab"] { font-size: 1.02rem; font-weight: 700; padding: 10px 18px; }
div.stButton > button { border-radius: 10px; font-weight: 600; }
[data-testid="stExpander"] { border-radius: 12px; }
</style>""", unsafe_allow_html=True)


def won(v):
    if v >= 100_000_000:
        return f"{v/100_000_000:,.2f}억 원"
    if v >= 10_000:
        return f"{v/10_000:,.0f}만 원"
    return f"{v:,.0f}원"


# ──────────────────────────────────────────────
# 4. Home 화면
# ──────────────────────────────────────────────

def page_home():
    if BG_PATH is not None:
        b64 = bg_to_base64(str(BG_PATH), BG_PATH.stat().st_mtime)
        bg_css = (f"linear-gradient(rgba(0,0,0,0.65), rgba(0,0,0,0.85)), "
                  f"url('data:image/jpeg;base64,{b64}')")
    else:
        bg_css = "linear-gradient(135deg, #1b2a1f, #0d1b2a)"
        st.sidebar.warning("배경 이미지를 찾지 못해 단색 배경을 사용합니다. "
                           "background.jpg를 app.py와 같은 위치에 올려주세요.")
    st.markdown(f"""
    <style>
    .stApp {{ background: {bg_css}; background-size: cover; background-attachment: fixed; }}
    .stApp h1,.stApp h2,.stApp h3,.stApp p,.stApp li,.stApp span,.stApp label,.stApp div {{ color:#f5f5f5; }}
    .card {{ background: rgba(255,255,255,0.10); border:1px solid rgba(255,255,255,0.25);
             border-radius:14px; padding:20px; height:100%; }}
    .big {{ font-size:3rem; font-weight:800; line-height:1.25; }}
    .card {{ transition: transform .2s, background .2s; }}
    .card:hover {{ transform: translateY(-4px); background: rgba(255,255,255,0.16); }}
    .kpi {{ text-align:center; padding:18px 10px; border-radius:14px; background: rgba(255,255,255,0.08);
            border:1px solid rgba(255,255,255,0.2); }}
    .kpi b {{ display:block; font-size:2rem; color:#A5D6A7; }}
    .kpi span {{ font-size:.85rem; opacity:.85; }}
    section[data-testid="stSidebar"] {{ background: rgba(12,22,16,0.92); }}
    section[data-testid="stSidebar"] * {{ color:#f5f5f5; }}
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.css');
    html, body, .stApp, button {{ font-family:'Pretendard','Malgun Gothic',sans-serif; }}
    </style>""", unsafe_allow_html=True)

    st.markdown('<p class="big">🌳 충남대 중앙도서관 앞 광장<br>열섬 완화 시뮬레이터</p>', unsafe_allow_html=True)
    st.markdown("##### 탈리그닌 목재 스펀지 기반 LID(저영향개발) 기법으로 도심 열섬을 낮춘다")
    st.button("🚀 시뮬레이터 시작하기", type="primary",
              on_click=lambda: st.session_state.update(page="열섬 완화 시뮬레이터"))
    k1, k2, k3, k4 = st.columns(4)
    k1.markdown('<div class="kpi"><b>50~64℃</b><span>한낮 아스팔트 표면온도<br>(대전 보도)</span></div>', unsafe_allow_html=True)
    k2.markdown('<div class="kpi"><b>6.4℃↓</b><span>살수 후 도로면 온도 저하<br>(서울시 조사)</span></div>', unsafe_allow_html=True)
    k3.markdown('<div class="kpi"><b>30~60분</b><span>살수 효과 지속시간<br>(서울시 조사)</span></div>', unsafe_allow_html=True)
    k4.markdown('<div class="kpi"><b>3종</b><span>비교 소재<br>우드칩·스펀지·바이오차</span></div>', unsafe_allow_html=True)
    st.divider()

    st.header("1. 프로젝트 배경")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown('<div class="card"><h4>🔥 도심 열섬</h4>'
                    '아스팔트·콘크리트 포장은 열을 흡수·저장해 한여름 지표면 온도가 50℃ 가까이 오릅니다.</div>',
                    unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="card"><h4>🚿 살수차의 한계</h4>'
                    '물을 뿌려도 곧 증발해 냉각 효과가 30~60분 정도만 유지되고, 물·인력·연료가 계속 듭니다.</div>',
                    unsafe_allow_html=True)
    with c3:
        st.markdown('<div class="card"><h4>🌧️ 빗물 유출</h4>'
                    '불투수 포장 때문에 빗물이 그대로 흘러가 저류·재활용이 되지 않습니다.</div>',
                    unsafe_allow_html=True)

    st.header("2. 해결방안: 목질계 다공성 흡착제")
    st.write("목재의 리그닌을 제거한 **탈리그닌 목재 스펀지**는 구조가 다공성이라 물을 많이 머금었다가 "
             "천천히 증발시키며 열을 빼앗습니다(증발냉각). 저렴한 **우드칩**, 탄소를 안정적으로 저장하는 **목재 바이오차**와 비교해 선택할 수 있습니다. "
             "핵심은 살수차처럼 하루 여러 번 물을 뿌리는 대신, **빗물을 한 번 저장해 오래 유지**하는 것입니다.")
    t1, t2, t2b, t3 = st.columns(4)
    t1.markdown(f"""<div class="card"><h4>🪵 우드칩</h4>
    단가 {MATERIALS['우드칩']['cost']:,}원/m²<br>온도 저감 {MATERIALS['우드칩']['drop']}℃<br>
    보수량 약 {MATERIALS['우드칩']['water']:.1f} L/m²</div>""", unsafe_allow_html=True)
    t2.markdown(f"""<div class="card"><h4>🧽 탈리그닌 스펀지</h4>
    단가 {MATERIALS['탈리그닌 스펀지']['cost']:,}원/m²<br>온도 저감 {MATERIALS['탈리그닌 스펀지']['drop']}℃<br>
    보수량 약 {MATERIALS['탈리그닌 스펀지']['water']:.1f} L/m²</div>""", unsafe_allow_html=True)
    t2b.markdown(f"""<div class="card"><h4>⚫ 목재 바이오차</h4>
    단가 {MATERIALS['목재 바이오차']['cost']:,}원/m²<br>온도 저감 {MATERIALS['목재 바이오차']['drop']}℃<br>
    보수량 약 {MATERIALS['목재 바이오차']['water']:.1f} L/m²</div>""", unsafe_allow_html=True)
    t3.markdown(f"""<div class="card"><h4>🚚 일반 살수차(대조군)</h4>
    1회 {TRUCK['cost_per_run']}원/m²<br>도로면 {TRUCK['drop']}℃↓(일시적)<br>
    지속 30~60분</div>""", unsafe_allow_html=True)

    st.header("3. 3대 기대효과")
    e1, e2, e3 = st.columns(3)
    e1.markdown('<div class="card"><h4>😎 열 쾌적성</h4>지표면 온도를 낮춰 보행자의 체감 더위를 줄입니다.</div>',
                unsafe_allow_html=True)
    e2.markdown('<div class="card"><h4>💧 빗물 저류</h4>비가 올 때 물을 머금어 유출을 줄이고, 맑은 날 냉각에 다시 씁니다.</div>',
                unsafe_allow_html=True)
    e3.markdown('<div class="card"><h4>🌫️ 재비산먼지 억제</h4>수분을 유지해 먼지가 다시 날리는 것을 막습니다.</div>',
                unsafe_allow_html=True)
    st.info("👈 왼쪽 메뉴에서 **열섬 완화 시뮬레이터**를 선택해 직접 시공 구역을 그려 보세요.")


# ──────────────────────────────────────────────
# 5. 시뮬레이터 화면
# ──────────────────────────────────────────────

def page_sim():
    inject_css()
    st.markdown('<div class="hero"><div class="hero-t">🌡️ 열섬 완화 시뮬레이터</div>'
                '<div class="hero-s">충남대 중앙도서관 앞 광장 · 목질계 흡착제 LID vs 일반 살수차</div></div>',
                unsafe_allow_html=True)
    st.caption("① 사이드바에서 소재·기준 온도 선택 → ② 지도에 시공 구역 그리기 → ③ 결과·비교가 즉시 계산됩니다.")

    for k, v in (("rect", None), ("map_ver", 0)):
        if k not in st.session_state:
            st.session_state[k] = v

    # ---- 사이드바 입력 ----
    with st.sidebar:
        st.header("⚙️ 입력값")
        material = st.radio("소재 선택", list(MATERIALS.keys()))
        map_mode = st.radio("지도 방식", ["실제 지도(GIS) - 영역 그리기", "이미지 지도 - 드래그"],
                            help="실제 지도: 위성사진 위에 다각형·사각형을 그리면 면적이 자동 계산됩니다.")
        gis_mode = map_mode.startswith("실제")
        if gis_mode:
            with st.expander("📍 지도 중심 좌표"):
                lat = st.number_input("위도", value=CNU_LAT, format="%.5f")
                lon = st.number_input("경도", value=CNU_LON, format="%.5f")
            map_w_m = 100.0
        else:
            lat, lon = CNU_LAT, CNU_LON
            map_w_m = st.number_input("지도 가로 폭의 실제 길이 (m)", 10.0, 2000.0, 100.0, 5.0,
                                      help="⚠ 기본값 100m는 임시값입니다. 지도 거리재기로 실측해 입력하세요.")
        total_m2 = st.number_input("광장 전체 면적 (m²)", 100.0, 1_000_000.0, 5000.0, 100.0)
        st.markdown("---")
        st.markdown("#### 🌡️ 기준 지표면 온도")
        TEMP_MODES = ["🌐 실시간 기상", "☀️ 여름 평균 한낮", "✋ 직접 입력"]
        if "temp_mode" not in st.session_state:
            st.session_state.temp_mode = TEMP_MODES[0]
        if st.button("☀️ 여름 평균 최저·최고 기온 보기", width="stretch",
                     help="여름철 기온 분석을 열고, 기준 지표면 온도를 '여름 평균 한낮'으로 바꿉니다."):
            st.session_state.show_summer = True
            st.session_state.temp_mode = TEMP_MODES[1]
        temp_mode = st.radio("기준 온도 방식", TEMP_MODES, key="temp_mode",
                             help="실시간: 지금 날씨 / 여름 평균 한낮: 최근 N년 6~8월 평균 최고기온+한낮 일사 / 직접 입력")
        live = temp_mode == TEMP_MODES[0]
        wx = None
        scale = 1.0
        base_temp = None
        if live:
            wx = fetch_weather(lat, lon)
            if wx:
                base_temp = est_surface(wx["air"], wx["rad"])
                scale = max(0.0, min(1.0, wx["rad"] / SOLAR_REF))
                st.success(f"{wx['time']} 기준 · 기온 {wx['air']:.1f}℃ · 일사 {wx['rad']:.0f} W/m²")
            else:
                st.warning("실시간 기상을 불러오지 못해 수동 입력으로 전환합니다.")
        elif temp_mode == TEMP_MODES[1]:
            ss = fetch_summer_stats(lat, lon, st.session_state.get("summer_years", 5))
            if ss:
                base_temp = ss["total"]["avg_max"] + SOLAR_K * ss["noon_rad"]
                scale = max(0.0, min(1.0, ss["noon_rad"] / SOLAR_REF))
                st.success(f"{ss['start']}~{ss['end']} 여름 평균 최고 {ss['total']['avg_max']:.1f}℃ · 한낮 일사 {ss['noon_rad']:.0f} W/m²")
            else:
                st.warning("여름 통계를 불러오지 못해 수동 입력으로 전환합니다.")
        if base_temp is None:
            base_temp = st.slider("기준 지표면 온도 (℃)", 20.0, 65.0, 50.0, 0.5,
                                  help="시공 전 포장면 온도 가정")
        else:
            st.metric("시공 전 포장면 온도(추정)", f"{base_temp:.1f} ℃")
        st.markdown("---")
        st.markdown("**살수차 비교 조건**")
        runs = st.slider("하루 살수 횟수 (회)", 1, 20, 3, help="살수차는 효과가 30~60분이라 반복 살수가 필요합니다.")
        window_h = st.slider("냉각이 필요한 시간 (시간)", 4, 14, 10, help="예: 오전 9시~오후 7시 = 10시간")
        if st.button("적용 구역 초기화"):
            st.session_state.rect = None
            st.session_state.map_ver += 1
            st.rerun()
        if st.button("광장 전체에 적용"):
            st.session_state.rect = "ALL"

    banner = st.container()
    tabs = st.tabs(["🗺️ 구역 지정·결과", "🌤️ 기온 분석", "⚖️ 소재·살수차 비교", "📚 계산식·출처"])
    with tabs[0]:
        if gis_mode:
            left, right = st.columns([3, 2])
            with left:
                applied_m2 = gis_map_area(lat, lon, st.session_state.map_ver)
                st.caption("지도 왼쪽 위 도구로 다각형/사각형을 그리면 면적이 자동 계산됩니다. 여러 개를 그리면 합산됩니다.")
            w_px, m_per_px = None, None
        else:
            if MAP_PATH is None:
                st.error("지도 이미지(library_map.png)를 찾지 못했습니다.")
                st.write("서버가 찾은 이미지 파일:", [p.name for p in IMAGES] or "없음")
                st.stop()
            img = Image.open(MAP_PATH).convert("RGB")
            w_px, h_px = img.size
            m_per_px = map_w_m / w_px

            # ---- 지도 + 드래그 선택 ----
            step_x, step_y = max(w_px // 40, 1), max(h_px // 40, 1)
            gx = list(range(0, w_px + 1, step_x))
            gy = list(range(0, h_px + 1, step_y))
            pts_x = [x for y in gy for x in gx]
            pts_y = [y for y in gy for x in gx]

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=pts_x, y=pts_y, mode="markers",
                                     marker=dict(size=14, opacity=0), hoverinfo="skip", showlegend=False))
            fig.add_layout_image(dict(source=img, xref="x", yref="y", x=0, y=h_px, sizex=w_px, sizey=h_px,
                                      sizing="stretch", layer="below"))
            fig.update_xaxes(range=[0, w_px], visible=False, constrain="domain")
            fig.update_yaxes(range=[0, h_px], visible=False, scaleanchor="x", scaleratio=1)
            fig.update_layout(dragmode="select", margin=dict(l=0, r=0, t=0, b=0), height=560,
                              newselection=dict(line=dict(color="red", width=2)))

            rect = st.session_state.rect
            use_slider = False
            left, right = st.columns([3, 2])
            with left:
                try:
                    event = st.plotly_chart(fig, key=f"map_{st.session_state.map_ver}",
                                            on_select="rerun", selection_mode="box",
                                            width="stretch")
                    box = event.selection.box if event and event.selection else []
                    if box:
                        bx, by = box[0]["x"], box[0]["y"]
                        st.session_state.rect = (min(bx), min(by), max(bx), max(by))
                except TypeError:
                    use_slider = True
                    st.plotly_chart(fig, width="stretch")
                    st.warning("Streamlit 버전이 낮아 드래그를 쓸 수 없습니다. 아래 슬라이더로 구역을 지정하세요.")
                    x0, x1 = st.slider("가로 범위 (%)", 0, 100, (20, 60))
                    y0, y1 = st.slider("세로 범위 (%)", 0, 100, (20, 60))
                    st.session_state.rect = (w_px * x0 / 100, h_px * y0 / 100, w_px * x1 / 100, h_px * y1 / 100)

            rect = st.session_state.rect
            if rect == "ALL":
                applied_px2 = w_px * h_px
            elif rect:
                x0, y0, x1, y1 = rect
                x0, x1 = max(0, x0), min(w_px, x1)
                y0, y1 = max(0, y0), min(h_px, y1)
                applied_px2 = max(0, x1 - x0) * max(0, y1 - y0)
            else:
                applied_px2 = 0
            applied_m2 = applied_px2 * m_per_px ** 2

        # ---- 결과 ----
        r = calc(material, applied_m2, total_m2, base_temp, window_h, scale)
        t = calc_truck(applied_m2, total_m2, base_temp, runs, window_h, scale)
        with banner:
            st.markdown(
                f'<div class="chips"><span class="chip">🧱 {material}</span>'
                f'<span class="chip">🌡️ 시공 전 {base_temp:.1f}℃ ({temp_mode.split(" ", 1)[1]})</span>'
                f'<span class="chip">📐 적용 {r["applied"]:,.0f}㎡ ({r["ratio"]*100:.0f}%)</span>'
                f'<span class="chip good">❄️ 시공 후 {r["temp"]:.1f}℃ (-{r["drop"]:.1f}℃)</span></div>',
                unsafe_allow_html=True)

        with right:
            st.subheader(f"📊 결과 ({material})")
            if r["ratio"] == 0:
                st.info("지도를 드래그해 시공 구역을 지정해 주세요.")
            if applied_m2 > total_m2:
                st.warning("선택 면적이 광장 전체 면적보다 커서 100%로 처리했습니다. 지도 가로 폭·전체 면적을 확인하세요.")
            a, b = st.columns(2)
            a.metric("적용 면적", f"{r['applied']:,.0f} m²")
            b.metric("적용 비율", f"{r['ratio']*100:.1f} %")
            a.metric("지표면 예상 온도", f"{r['temp']:.1f} ℃", f"-{r['drop']:.2f} ℃", delta_color="inverse")
            b.metric("시공 예산", won(r["budget"]))
            a.metric("빗물 저류량", f"{r['storage_l']/1000:,.1f} m³")
            b.metric("냉각 지속시간(추정)", f"약 {r['hours']:.1f} 시간")
            a.metric("탄소 저장량(소재 고정)", f"{r['carbon']:,.0f} kg C")
            b.metric("재비산먼지 억제", DUST_LABEL[r["dust"]])
            a.metric("하루 누적 냉각", f"{r['cum']:,.1f} ℃·h", help="온도 저감폭 × 냉각 유지시간(냉각 필요 시간 이내)")
            b.metric(f"살수차 {runs}회 누적 냉각", f"{t['cum']:,.1f} ℃·h")

        st.divider()

    with tabs[1]:
        st.markdown(f"**현재 기준 온도 방식:** {temp_mode} → 시공 전 포장면 **{base_temp:.1f} ℃** (일사 보정 계수 {scale:.2f})")
        if st.session_state.get("show_summer", False) or temp_mode == TEMP_MODES[1]:
            st.subheader("☀️ 여름철(6~8월) 평균 최저·최고 기온")
            render_summer(lat, lon)
            if st.button("여름 분석 닫기"):
                st.session_state.show_summer = False
                st.rerun()
        else:
            st.info("사이드바의 **☀️ 여름 평균 최저·최고 기온 보기** 버튼을 누르면 여름철 분석이 열리고, 지표면 예상 온도도 함께 바뀝니다.")
        if live and wx:
            h = wx["hourly"]
            surf = [est_surface(a_, r_) for a_, r_ in zip(h["air"], h["rad"])]
            sc_h = [max(0.0, min(1.0, r_ / SOLAR_REF)) for r_ in h["rad"]]
            cooled = [sv - MATERIALS[material]["drop"] * r["ratio"] * c for sv, c in zip(surf, sc_h)]
            fh = go.Figure()
            fh.add_trace(go.Scatter(x=h["time"], y=h["air"], name="기온", line=dict(color="#90A4AE")))
            fh.add_trace(go.Scatter(x=h["time"], y=surf, name="포장면(시공 전, 추정)", line=dict(color="#E53935")))
            fh.add_trace(go.Scatter(x=h["time"], y=cooled, name=f"포장면(시공 후, {material})",
                                    line=dict(color=MATERIALS[material]["color"], width=3)))
            fh.update_layout(title="오늘 시간대별 예상 온도 (Open-Meteo 예보·관측 기반)", yaxis_title="℃",
                             height=340, margin=dict(t=50, b=10), legend=dict(orientation="h", y=-0.2))
            st.plotly_chart(fh, width="stretch")
            st.caption("포장면 온도 = 기온 + 0.022 × 일사량(가정식). 냉각 효과는 일사량에 비례해 줄어든다고 가정(700 W/m² 이상 100%).")

    with tabs[2]:
        # ---- 비교 그래프 ----
        st.subheader("⚖️ 소재 · 살수차 비교 (같은 시공 구역 기준)")
        results = {name: calc(name, applied_m2, total_m2, base_temp, window_h, scale) for name in MATERIALS}
        names = list(MATERIALS.keys()) + ["일반 살수차(1회)"]
        temps = [results[n]["temp"] for n in MATERIALS] + [t["temp"]]
        colors = [MATERIALS[n]["color"] for n in MATERIALS] + [TRUCK["color"]]

        g1, g2 = st.columns(2)
        with g1:
            f1 = go.Figure(go.Bar(x=names, y=temps, marker_color=colors,
                                  text=[f"{v:.1f}℃" for v in temps], textposition="outside"))
            f1.add_hline(y=base_temp, line_dash="dash", annotation_text=f"시공 전 {base_temp:.1f}℃")
            f1.update_layout(title="지표면 예상 온도", yaxis=dict(range=[base_temp - 12, base_temp + 3], title="℃"),
                             height=360, margin=dict(t=50, b=10))
            st.plotly_chart(f1, width="stretch")
        with g2:
            cums = [results[n]["cum"] for n in MATERIALS] + [t["cum"]]
            f2 = go.Figure(go.Bar(x=names, y=cums, marker_color=colors,
                                  text=[f"{v:,.1f}" for v in cums], textposition="outside"))
            f2.update_layout(title=f"하루 누적 냉각 (℃·시간, 살수차 {runs}회)", height=360, margin=dict(t=50, b=10))
            st.plotly_chart(f2, width="stretch")

        g3, g4 = st.columns(2)
        with g3:
            days = list(range(0, 91))
            f3 = go.Figure()
            for n in MATERIALS:
                f3.add_trace(go.Scatter(x=days, y=[(results[n]["budget"] + results[n]["opex_day"] * d) / 10000 for d in days],
                                        name=n, line=dict(color=MATERIALS[n]["color"])))
            f3.add_trace(go.Scatter(x=days, y=[t["opex_day"] * d / 10000 for d in days],
                                    name=f"살수차 {runs}회/일", line=dict(color=TRUCK["color"], dash="dash")))
            f3.update_layout(title="누적 비용 (만 원, 시공비 + 운영비)", xaxis_title="경과 일수", height=360,
                             margin=dict(t=50, b=10))
            st.plotly_chart(f3, width="stretch")
        with g4:
            waters = [results[n]["water_day"] / 1000 for n in MATERIALS] + [t["water_day"] / 1000]
            f4 = go.Figure(go.Bar(x=names, y=waters, marker_color=colors,
                                  text=[f"{v:,.1f}" for v in waters], textposition="outside"))
            f4.update_layout(title="하루 필요 물 (m³) - 목재 소재는 빗물 재충전 가정", height=360, margin=dict(t=50, b=10))
            st.plotly_chart(f4, width="stretch")

        # 회수 기간
        be_rows = []
        if t["opex_day"] > 0:
            for n in MATERIALS:
                gap = t["opex_day"] - results[n]["opex_day"]
                if gap > 0:
                    be_rows.append(f"- **{n}**: 시공비가 살수차 운영비보다 싸지는 시점 약 **{results[n]['budget']/gap:,.0f}일**")
        if be_rows:
            st.markdown("**💰 시공비 회수 기간 (살수차 대비, 가정값 기준)**\n" + "\n".join(be_rows))

        st.markdown("**지속성 비교:** 살수차는 1회 살수 후 약 "
                    f"{TRUCK['hours']}시간만 효과가 유지되어 {runs}회 살수해야 하고, 하루 물 {t['water_day']/1000:,.1f} m³가 듭니다. "
                    "목재 소재는 빗물을 한 번 저류해 몇 시간 동안 냉각을 유지합니다. "
                    "**순간 냉각은 살수차가 비슷하거나 더 크지만, 지속시간·반복 운영 부담에서 차이가 납니다.**")

    with tabs[3]:
        # ---- 수식 ----
        if gis_mode:
            scale_line = "- 실제 지도(GIS): 그린 다각형의 위경도를 평면(m)으로 환산해 신발끈 공식으로 면적 계산, 여러 도형은 합산"
        else:
            scale_line = f"- 지도 1픽셀의 실제 길이 `m_per_px = 지도 가로 폭(m) / 이미지 가로 픽셀` = {map_w_m:g} / {w_px} = **{m_per_px:.4f} m**"
        with st.expander("🧮 계산식 보기 (코드와 동일)"):
            st.markdown(f"""
    {scale_line}
    - 적용 면적(m²) = 선택 사각형 픽셀 면적 × m_per_px² = **{applied_m2:,.1f}**
    - 적용 비율 = 적용 면적 / 광장 전체 면적 (최대 100%) = **{r['ratio']*100:.1f}%**
    - 기준 온도(실시간) = 현재 기온 + 0.022 × 현재 일사량 / (여름 평균 한낮) = 평균 최고기온 + 0.022 × 12~15시 평균 일사량\n- 일사 보정 계수 = min(1, 일사량/700)
    - 지표면 예상 온도 = 기준 온도 − 소재별 저감폭 × 적용 비율 × 일사 보정 계수
    - 시공 예산 = 소재 단가 × 적용 면적
    - 빗물 저류량 = (두께 × 용적밀도 × 보수율) × 적용 면적
    - 냉각 지속시간 = 단위면적 저류량 / 증발속도(1.5 L/m²·h, 가정)
    - 탄소 저장량 = 두께 × 밀도 × 탄소함량(47%) × 적용 면적
    - 하루 누적 냉각(℃·h) = 온도 저감폭 × 적용 비율 × min(냉각 유지시간, 냉각 필요 시간)
    - 살수차 누적 냉각 = 6.4℃ × 적용 비율 × min(살수 횟수 × 0.75h, 냉각 필요 시간)
    - 누적 비용 = 시공비 + 일 운영비 × 경과 일수 (살수차는 시공비 0, 운영비 = 1회 비용 × 횟수 × 면적)
    - 먼지 억제 = 소재 등급 × 적용 비율 → 낮음/보통/높음
    """)

        with st.expander("📌 데이터 출처와 한계"):
            st.markdown("""
    **[문헌] 근거 있는 값**
    - 살수 후 도로면 온도 6.4℃↓, 인도 기온 1.5℃↓, 효과 30~60분: 서울시 보건환경연구원 조사(서울시 보도자료 2021, 동아일보 2025.7.23)
    - 대전 소방차 살수 시 지면 온도 약 10℃↓, 한낮 아스팔트 표면 50~64℃: TJB 대전방송 보도, 대전시 보도자료(미조성 구간 약 50℃)
    - 우드칩 용적밀도 0.293 g/cm³, 보수율 58.5%, 탄소 함량 43~50%: Minnesota Stormwater Manual
    - 목재 스펀지 흡수배율 0.65~2.24 g/g: Sengon wood sponge 연구(J. Renewable Materials, 2025)
    - 살수차 1km당 약 1t 살포: 동아일보 2025.7.23
    - 목재 바이오차 용적밀도 0.15~0.33 g/cm³, 보수율 50.6~179.4%(건중량 기준): Yargicoglu et al. 2015(USDA-ARS), Gliricidia 바이오차 연구(JSWC 2022)
    - 목재 바이오차 탄소함량 최대 92%(600℃): Water 2021, 13(19), 2613 (MDPI)

    **[추정] 위 문헌값으로 계산한 값**: 보수량, 빗물 저류량, 탄소 저장량, 냉각 지속시간

    **[가정] 근거 미확보 값**: 소재 단가, 우드칩·바이오차의 온도 저감폭, 스펀지 저감폭(살수 효과 수준으로 가정), 바이오차 탄소함량(80%), 목재 소재 일 운영비(0원), 하루 살수 횟수 기본값(3회), 시공 두께(5cm), 증발속도, 살수차 운영비, 먼지 억제 등급

    - 여름철 기온·일사 통계: Open-Meteo Archive API(ERA5 재분석)
    - 실시간 기온·일사량: Open-Meteo API(https://open-meteo.com), 위성지도: Esri World Imagery, 영역 그리기: Leaflet.draw(folium)

    **[가정] 실시간 연동 관련**: 포장면 온도 추정식(기온 + 0.022×일사량), 냉각 효과의 일사 비례 보정(700 W/m² 기준)

    **한계**: 온도는 적용 비율에 선형 비례한다고 단순화했습니다(주변 열 확산 미반영). 지도 축척은 입력한 가로 폭에 따라 달라집니다.
    """)


# ──────────────────────────────────────────────
# 6. 화면 전환
# ──────────────────────────────────────────────
page = st.sidebar.radio("📍 메뉴", ["프로젝트 소개(Home)", "열섬 완화 시뮬레이터"], key="page")
if page.startswith("프로젝트"):
    page_home()
else:
    page_sim()
