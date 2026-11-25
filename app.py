import json
import time
import streamlit as st
from google import genai
from google.genai import types
from pypdf import PdfReader

# =====================================================
# 0. 기본 설정
# =====================================================
st.set_page_config(page_title="금융공기업 AI 모의면접", page_icon="🎤")


def get_secret(name, default=None):
    """Streamlit Secrets에서 값을 꺼내요. 없으면 default를 돌려줘요."""
    try:
        return st.secrets[name]
    except Exception:
        return default


PASSWORD = get_secret("APP_PASSWORD", "pnumis")             # 과제 비밀번호
API_KEY = get_secret("GEMINI_API_KEY")                       # Gemini API 키 (코드에 직접 쓰지 않기!)
MODEL = get_secret("MODEL", "gemini-flash-latest")           # 먼저 써볼 AI 모델

# 먼저 써본 모델이 안 되면 차례대로 시도할 모델들
PREFERRED_MODELS = [MODEL, "gemini-flash-latest", "gemini-3.7-flash", "gemini-3.6-flash",
                    "gemini-flash-lite-latest", "gemini-3.5-flash-lite"]

# 기관 정보: 각 기관 홈페이지의 '인재상', '주요 사업'을 복사해서 더 채우면 질문이 더 정확해져요.
INSTITUTIONS = {
    "한국예탁결제원 (KSD)": "증권의 예탁·결제를 맡는 자본시장 핵심 인프라 기관. "
                         "전자증권제도 운영, 증권 결제, 펀드 운용 지원, 증권대행(주주명부 관리 등), "
                         "글로벌 증권 서비스 등을 수행한다. 본사는 부산.",
    "한국자산관리공사 (KAMCO)": "부실채권 인수·정리, 가계·기업의 재기 지원(채무조정 등), "
                            "국유재산 관리·개발, 공공자산 공매 시스템(온비드) 운영 등을 수행한다. 본사는 부산.",
    "기술보증기금": "기술력은 있지만 담보가 부족한 중소·벤처기업에 기술보증을 제공하고, "
              "기술평가와 창업·혁신기업 지원을 수행한다. 본사는 부산.",
    "한국주택금융공사 (HF)": "주택금융 전문 공기업. 주택연금, 보금자리론 등 정책 모기지, "
                         "전세자금 등 주택보증, 주택저당증권(MBS) 발행을 수행한다. 본사는 부산.",
}

# 면접관 유형
MODES = {
    "실무자 면접": "실무진 면접관이다. 직무 지식, 경험의 구체적인 과정과 역할, 업무 상황 대처를 묻는다.",
    "임원 면접": "임원 면접관이다. 가치관, 조직 적합성, 공공기관 직원으로서의 윤리의식과 장기 비전을 묻는다.",
    "압박 면접": "압박 면접관이다. 답변의 모순, 근거 부족, 과장된 부분을 집요하게 파고든다. 단, 인신공격은 하지 않는다.",
}

# 진행 방식
STYLES = ["연습 모드 (답변마다 피드백)", "실전 모드 (피드백은 마지막에)"]

# 질문 유형
QUESTION_TYPES = ["자소서 꼬리질문", "직무 지식", "기관·시사", "인성·가치관"]

# 점수 평가 항목
SCORE_ITEMS = ["논리성", "직무 이해도", "기관 이해도", "자소서 일관성"]

# 교수님·사용자가 바로 테스트해 볼 수 있는 예시 자소서 (가상의 지원자)
SAMPLE_RESUME = """[지원동기]
저는 자본시장이 안전하게 돌아가도록 뒷받침하는 금융 인프라에 관심을 갖고 지원했습니다. 금융·경제 학회에서 1년간 활동하며 기준금리 변화가 채권·주식시장에 미치는 영향을 분석했고, 이 과정에서 눈에 잘 띄지 않는 결제·예탁 시스템이 시장 신뢰의 기반이라는 점을 알게 되었습니다.

[직무 역량]
학회에서 한국은행 경제통계 데이터를 엑셀과 파이썬으로 정리해 금리와 가계대출 증가율의 관계를 분석하는 프로젝트를 맡았습니다. 데이터 출처마다 기준 시점이 달라 생긴 오류를 직접 찾아 수정했고, 그 결과 발표 자료의 신뢰도를 높일 수 있었습니다.

[협업 경험]
카페 아르바이트에서 마감 정산 오차가 자주 발생하자 체크리스트를 만들어 동료들과 공유했습니다. 3개월 동안 정산 오차가 거의 사라졌고, 작은 절차 개선이 조직 전체의 정확성을 높인다는 것을 배웠습니다.

[입사 후 포부]
입사 후에는 정확성과 책임감을 바탕으로 고객이 믿고 맡길 수 있는 금융 서비스를 만드는 데 기여하고 싶습니다."""


# =====================================================
# 1. 비밀번호 화면
# =====================================================
if "login" not in st.session_state:
    st.session_state.login = False

if not st.session_state.login:
    st.title("🎤 금융공기업 AI 모의면접")
    st.write("비밀번호를 입력해야 사용할 수 있어요.")
    pw = st.text_input("비밀번호", type="password")
    if st.button("입장하기"):
        if pw.strip() == PASSWORD:
            st.session_state.login = True
            st.rerun()
        else:
            st.error("비밀번호가 틀렸어요.")
    st.stop()  # 로그인 전에는 아래 코드가 실행되지 않아요.

if not API_KEY:
    st.error("Gemini API 키가 설정되지 않았어요. Streamlit Cloud의 Secrets에 GEMINI_API_KEY를 넣어주세요.")
    st.stop()

# v1beta 주소를 써야 최신 모델과 '-latest' 이름을 쓸 수 있어요.
client = genai.Client(api_key=API_KEY, http_options=types.HttpOptions(api_version="v1beta"))


@st.cache_data(ttl=3600, show_spinner=False)
def find_models():
    """내 API 키로 쓸 수 있는 모델 이름들을 구글에 물어봐요. (1시간 동안 기억)"""
    try:
        names = []
        for m in client.models.list():
            if "generateContent" in (m.supported_actions or []):
                names.append(m.name.replace("models/", ""))
        return names
    except Exception:
        return []  # 목록을 못 받아오면 미리 정해둔 모델들로 시도해요.


def model_candidates():
    """시도할 모델 순서를 정해요. 한 번 성공한 모델이 있으면 그걸 제일 먼저 써요."""
    available = find_models()
    if available:
        candidates = [m for m in PREFERRED_MODELS if m in available]
        skip = ["tts", "image", "live", "audio", "embedding", "robotics"]
        candidates += [n for n in available
                       if "flash" in n and not any(word in n for word in skip)]
    else:
        candidates = list(PREFERRED_MODELS)
    good = st.session_state.get("good_model")
    if good:
        candidates.insert(0, good)
    return list(dict.fromkeys(candidates))  # 중복 없애기 (순서는 유지)


# =====================================================
# 2. 기억해 둘 값들 (새로고침 전까지 유지)
# =====================================================
def reset():
    """면접 진행 상태만 지워요. (자소서와 지난 점수 기록은 남겨둬요)"""
    st.session_state.started = False   # 면접이 시작됐는지
    st.session_state.messages = []     # 대화 기록
    st.session_state.answered = 0      # 지금까지 답변한 개수
    st.session_state.report = None     # 최종 리포트
    st.session_state.settings = {}     # 면접 설정
    st.session_state.hint = None       # 힌트 내용
    st.session_state.q_start = None    # 질문이 나온 시각 (답변 시간 계산용)


if "started" not in st.session_state:
    reset()
if "resume" not in st.session_state:
    st.session_state.resume = ""       # 자소서 입력칸 내용
if "history" not in st.session_state:
    st.session_state.history = []     # 지금까지 본 면접들의 점수 기록


# =====================================================
# 3. AI에게 물어보는 함수들
# =====================================================
def ask_ai(contents, system_prompt, json_mode=False):
    """Gemini에게 대화를 보내고 답변 글자를 받아와요. 모델이 안 되면 다음 모델로 다시 시도해요."""
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type="application/json" if json_mode else "text/plain",
    )
    errors = []
    for model in model_candidates()[:5]:  # 최대 5개까지만 시도
        try:
            response = client.models.generate_content(model=model, contents=contents, config=config)
            st.session_state.good_model = model  # 성공한 모델은 기억해 둬요.
            return response.text
        except Exception as e:
            errors.append(f"- {model}: {str(e)[:200]}")
    raise RuntimeError("\n".join(errors))


def safe_ask(contents, system_prompt, json_mode=False):
    """오류가 나도 앱이 멈추지 않게 감싸요."""
    try:
        return ask_ai(contents, system_prompt, json_mode)
    except Exception as e:
        st.error("AI 응답 중 오류가 났어요. 잠시 후 다시 시도해 주세요.")
        with st.expander("오류 자세히 보기"):
            st.code(str(e), language=None)
        return None


def make_interview_prompt(s):
    """면접관 역할을 정해주는 지시문을 만들어요."""
    if s["style"] == STYLES[0]:
        style_rule = ("지원자가 답하면 먼저 '💬 한 줄 피드백:'으로 1~2문장 피드백을 주고, 그다음 질문을 한다.")
    else:
        style_rule = ("실전 면접처럼 진행한다. 답변에 대한 평가나 피드백은 절대 말하지 말고, "
                      "'네, 알겠습니다.' 정도의 짧은 반응 뒤 바로 다음 질문을 한다.")

    intro_rule = "- 질문 1은 반드시 '1분 자기소개'를 요청하는 질문으로 한다.\n" if s["intro"] else ""
    extra = f"\n[기관 추가 정보 (지원자가 입력)]\n{s['extra']}\n" if s["extra"].strip() else ""

    return f"""
너는 {s['inst']}의 면접관이다. {MODES[s['mode']]}

[기관 정보]
{INSTITUTIONS[s['inst']]}
{extra}
[지원 직무]
{s['job']}

[지원자 자기소개서]
{s['resume']}

[진행 규칙]
- 질문은 총 {s['n_q']}개다. 한 번에 질문은 딱 하나만 한다.
- 질문 앞에는 반드시 '**질문 k/{s['n_q']}**' 형식으로 번호를 붙인다.
{intro_rule}- 질문은 다음 유형을 골고루 섞는다: {', '.join(s['q_types'])}.
- '자소서 꼬리질문'은 자기소개서에 나온 구체적인 경험과 주장을 근거로 파고드는 질문이다.
- 직전 답변이 모호하거나 근거가 약하면 그 부분을 다시 파고드는 꼬리질문을 한다.
- {style_rule}
- 한국어 존댓말로, 실제 면접관처럼 간결하게 말한다.
"""


HINT_PROMPT = """
너는 면접 코치다. 면접관의 마지막 질문에 지원자가 어떻게 답하면 좋을지 힌트를 준다.
완성된 모범답안은 쓰지 말고, 아래 3가지를 짧은 bullet로 알려준다.
1) 질문 의도
2) 넣으면 좋은 내용 (지원자 자기소개서의 어떤 경험을 쓰면 좋은지 짚어준다)
3) 추천 답변 구조 (예: 결론 → 근거 → 경험 → 입사 후 기여)
"""

REPORT_PROMPT = """
너는 금융공기업 면접 평가 전문가다. 아래 면접 기록을 평가해서 JSON으로만 답한다.
점수는 0~100 사이 정수다. 형식은 다음과 같다.
{
  "scores": {"논리성": 0, "직무 이해도": 0, "기관 이해도": 0, "자소서 일관성": 0},
  "summary": "총평 2~3문장",
  "habit": "답변 길이와 답변 시간 통계를 보고 답변 습관에 대한 코멘트 1~2문장",
  "good": ["잘한 점 1", "잘한 점 2"],
  "improve": ["보완할 점 1", "보완할 점 2"],
  "per_question": [
    {"question": "질문 요약", "comment": "이 답변에 대한 평가", "better_answer": "개선된 답변 예시"}
  ]
}
"""


def to_contents(messages):
    """대화 기록을 Gemini가 읽는 형식으로 바꿔요."""
    contents = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        text = m.get("api", m["content"])  # AI에게만 보내는 진행 메모가 있으면 그걸 보내요.
        contents.append({"role": role, "parts": [{"text": text}]})
    return contents


def make_transcript(messages):
    """화면에 보이는 대화만 모아서 면접 기록 글로 만들어요."""
    lines = []
    for m in messages:
        if m.get("hidden"):
            continue
        who = "지원자" if m["role"] == "user" else "면접관"
        lines.append(f"{who}: {m['content']}")
    return "\n\n".join(lines)


def answer_stats(messages):
    """지원자 답변의 평균 글자 수와 평균 답변 시간을 계산해요."""
    answers = [m for m in messages if m["role"] == "user" and not m.get("hidden")]
    if not answers:
        return {"count": 0, "avg_len": 0, "avg_sec": 0}
    lengths = [len(m["content"]) for m in answers]
    seconds = [m["sec"] for m in answers if m.get("sec")]
    return {
        "count": len(answers),
        "avg_len": round(sum(lengths) / len(lengths)),
        "avg_sec": round(sum(seconds) / len(seconds)) if seconds else 0,
    }


def get_grade(avg):
    """평균 점수를 등급으로 바꿔요."""
    if avg >= 90:
        return "S"
    if avg >= 80:
        return "A"
    if avg >= 70:
        return "B"
    if avg >= 60:
        return "C"
    return "D"


def make_report(s, messages):
    """면접이 끝나면 점수 리포트를 만들어요."""
    stats = answer_stats(messages)
    text = (f"기관: {s['inst']} / 직무: {s['job']} / 면접 유형: {s['mode']}\n"
            f"답변 통계: 답변 {stats['count']}개, 평균 {stats['avg_len']}자, 평균 {stats['avg_sec']}초\n\n"
            f"[자기소개서]\n{s['resume']}\n\n[면접 기록]\n{make_transcript(messages)}")
    raw = safe_ask([{"role": "user", "parts": [{"text": text}]}], REPORT_PROMPT, json_mode=True)
    if raw is None:
        return None
    try:
        report = json.loads(raw)
    except Exception:
        return {"raw": raw, "stats": stats}  # JSON이 깨졌으면 글 그대로 보여줘요.

    # 평균 점수와 등급은 파이썬으로 직접 계산해요.
    scores = report.get("scores", {})
    numbers = [v for v in scores.values() if isinstance(v, (int, float))]
    report["avg"] = round(sum(numbers) / len(numbers)) if numbers else 0
    report["grade"] = get_grade(report["avg"])
    report["stats"] = stats
    return report


def report_to_text(s, report, messages):
    """다운로드용 리포트(.txt) 내용을 만들어요."""
    stats = report.get("stats", {})
    lines = ["[AI 모의면접 결과 리포트]",
             f"기관: {s['inst']}", f"직무: {s['job']}", f"면접관 유형: {s['mode']}",
             f"진행 방식: {s['style']}", ""]
    if "raw" in report:
        lines.append(report["raw"])
    else:
        lines.append(f"■ 평균 {report['avg']}점 / 등급 {report['grade']}")
        for k, v in report.get("scores", {}).items():
            lines.append(f"  - {k}: {v}점")
        lines += ["", "■ 총평", report.get("summary", ""), "",
                  "■ 답변 습관",
                  f"  답변 {stats.get('count', 0)}개 · 평균 {stats.get('avg_len', 0)}자 · 평균 {stats.get('avg_sec', 0)}초",
                  "  " + report.get("habit", ""), "", "■ 잘한 점"]
        lines += [f"  - {x}" for x in report.get("good", [])]
        lines += ["", "■ 보완할 점"]
        lines += [f"  - {x}" for x in report.get("improve", [])]
        lines += ["", "■ 질문별 피드백"]
        for i, q in enumerate(report.get("per_question", []), 1):
            lines += [f"{i}. {q.get('question', '')}",
                      f"  평가: {q.get('comment', '')}",
                      f"  개선 답변 예시: {q.get('better_answer', '')}", ""]
    lines += ["", "■ 면접 기록", make_transcript(messages)]
    return "\n".join(lines)


def finish_interview():
    """면접을 끝내고 리포트를 만들어요."""
    s = st.session_state.settings
    with st.spinner("면접 결과를 평가하고 있어요..."):
        report = make_report(s, st.session_state.messages)
    if report:
        st.session_state.report = report
        if "raw" not in report:
            st.session_state.history.append({
                "회차": len(st.session_state.history) + 1,
                "기관": s["inst"],
                "면접관": s["mode"],
                "평균": report["avg"],
                "등급": report["grade"],
            })
        st.rerun()


# =====================================================
# 4. 자소서 입력을 도와주는 함수들 (버튼을 누르면 실행돼요)
# =====================================================
def fill_sample():
    st.session_state.resume = SAMPLE_RESUME


def load_file():
    """올린 파일(.txt, .pdf)에서 글자를 읽어서 자소서 칸에 넣어요."""
    f = st.session_state.resume_file
    if f is None:
        return
    try:
        if f.name.lower().endswith(".pdf"):
            reader = PdfReader(f)
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        else:
            data = f.read()
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = data.decode("cp949", errors="ignore")  # 윈도우 메모장 한글 파일 대비
        st.session_state.resume = text.strip()
        st.session_state.file_msg = None
    except Exception:
        st.session_state.file_msg = "파일을 읽지 못했어요. 내용을 복사해서 붙여넣어 주세요."


# =====================================================
# 5. 사이드바: 면접 설정
# =====================================================
with st.sidebar:
    st.header("⚙️ 면접 설정")
    inst = st.selectbox("지원 기관", list(INSTITUTIONS.keys()))
    job = st.text_input("지원 직무", "금융사무 (일반)")
    extra = st.text_area("기관 인재상·최근 이슈 (선택)", height=90,
                         placeholder="기관 홈페이지의 인재상이나 최근 뉴스를 붙여넣으면 질문이 더 정확해져요.")
    mode = st.radio("면접관 유형", list(MODES.keys()))
    style = st.radio("진행 방식", STYLES)
    q_types = st.multiselect("질문 유형", QUESTION_TYPES, default=QUESTION_TYPES[:3])
    intro = st.checkbox("1분 자기소개로 시작하기", value=True)
    n_q = st.slider("질문 개수", min_value=3, max_value=10, value=5)

    st.divider()
    st.subheader("📄 자기소개서")
    st.file_uploader("파일로 올리기 (.txt, .pdf)", type=["txt", "pdf"],
                     key="resume_file", on_change=load_file)
    if st.session_state.get("file_msg"):
        st.warning(st.session_state.file_msg)
    st.button("예시 자소서 넣기", on_click=fill_sample)
    resume = st.text_area("자기소개서 내용", key="resume", height=250,
                          placeholder="자기소개서 내용을 붙여넣거나, 위에서 파일을 올려주세요.")
    st.caption(f"{len(resume)}자")

    st.divider()
    start = st.button("🎬 면접 시작", type="primary")
    if st.button("🔄 처음부터 다시"):
        reset()
        st.rerun()


# =====================================================
# 6. 면접 시작 버튼을 눌렀을 때
# =====================================================
if start:
    if len(resume.strip()) < 50:
        st.sidebar.warning("자기소개서를 50자 이상 넣어 주세요.")
    elif not q_types:
        st.sidebar.warning("질문 유형을 하나 이상 골라 주세요.")
    else:
        reset()
        s = {"inst": inst, "job": job, "extra": extra, "mode": mode, "style": style,
             "q_types": q_types, "intro": intro, "n_q": n_q, "resume": resume}
        st.session_state.settings = s
        # AI에게만 보내는 첫 메시지 (화면에는 안 보여요)
        first = {"role": "user", "content": "", "hidden": True,
                 "api": f"면접을 시작해 주세요. 짧게 인사한 뒤 질문 1/{n_q}을 해 주세요."}
        with st.spinner("면접관이 자기소개서를 읽고 있어요..."):
            reply = safe_ask(to_contents([first]), make_interview_prompt(s))
        if reply:
            st.session_state.messages = [first, {"role": "assistant", "content": reply}]
            st.session_state.started = True
            st.session_state.q_start = time.time()
            st.rerun()


# =====================================================
# 7. 메인 화면
# =====================================================
st.title("🎤 금융공기업 AI 모의면접")

if not st.session_state.started:
    # 아직 시작 전: 사용 방법 안내
    st.markdown("""
자기소개서를 바탕으로 **꼬리질문**을 하는 AI 면접관이에요.

**사용 방법**
1. 왼쪽 사이드바에서 **지원 기관, 직무, 면접관 유형, 진행 방식, 질문 유형**을 골라요.
2. **자기소개서**를 붙여넣거나 파일(.txt, .pdf)로 올려요. 바로 써보려면 **예시 자소서 넣기**를 눌러요.
3. **면접 시작**을 누르면 면접관이 첫 질문을 해요.
4. 답이 막히면 **💡 힌트 보기**, 중간에 끝내려면 **⏹️ 여기까지 평가받기**를 눌러요.
5. 면접이 끝나면 **점수·등급 리포트**를 보고 .txt 파일로 다운로드할 수 있어요.

**진행 방식**
- **연습 모드**: 답변할 때마다 한 줄 피드백을 받아요.
- **실전 모드**: 중간 피드백 없이 진행하고, 마지막에 한 번에 평가받아요.
""")
    st.caption("※ 모바일에서는 왼쪽 위 화살표(>)를 눌러 사이드바를 열어요.")
    st.stop()

s = st.session_state.settings
st.caption(f"{s['inst']} · {s['job']} · {s['mode']} · {s['style'].split(' ')[0]} {s['style'].split(' ')[1]}")

# 지금까지의 대화 보여주기
for m in st.session_state.messages:
    if m.get("hidden"):
        continue
    avatar = "🧑‍💼" if m["role"] == "assistant" else "🙋"
    with st.chat_message(m["role"], avatar=avatar):
        st.markdown(m["content"])
        if m["role"] == "user" and m.get("sec"):
            st.caption(f"⏱️ {m['sec']}초 · {len(m['content'])}자")

# ---------- 면접 진행 중 ----------
if st.session_state.report is None:
    st.progress(st.session_state.answered / s["n_q"],
                text=f"답변 {st.session_state.answered} / {s['n_q']}")

    # 힌트 보기 / 여기까지 평가받기 버튼
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💡 힌트 보기"):
            text = (f"[지원자 자기소개서]\n{s['resume']}\n\n[지금까지의 면접]\n"
                    f"{make_transcript(st.session_state.messages)}")
            with st.spinner("힌트를 만들고 있어요..."):
                st.session_state.hint = safe_ask([{"role": "user", "parts": [{"text": text}]}], HINT_PROMPT)
    with col2:
        if st.session_state.answered >= 1 and st.button("⏹️ 여기까지 평가받기"):
            finish_interview()

    if st.session_state.hint:
        st.info(st.session_state.hint)

    answer = st.chat_input("답변을 입력하세요")
    if answer:
        k = st.session_state.answered + 1
        sec = round(time.time() - st.session_state.q_start) if st.session_state.q_start else None
        with st.chat_message("user", avatar="🙋"):
            st.markdown(answer)

        if k < s["n_q"]:
            # 아직 질문이 남았으면: (연습 모드면 피드백 +) 다음 질문
            note = (f"\n\n(진행 메모: 지원자의 {k}번째 답변입니다. "
                    f"진행 규칙에 맞게 반응한 뒤 질문 {k + 1}/{s['n_q']}을 해 주세요.)")
            new_msg = {"role": "user", "content": answer, "api": answer + note, "sec": sec}
            with st.spinner("면접관이 답변을 듣고 있어요..."):
                reply = safe_ask(to_contents(st.session_state.messages + [new_msg]),
                                 make_interview_prompt(s))
            if reply:
                st.session_state.messages += [new_msg, {"role": "assistant", "content": reply}]
                st.session_state.answered = k
                st.session_state.hint = None
                st.session_state.q_start = time.time()
                st.rerun()
        else:
            # 마지막 답변이면: 리포트 만들기
            st.session_state.messages.append({"role": "user", "content": answer, "sec": sec})
            st.session_state.answered = k
            st.session_state.hint = None
            finish_interview()

# ---------- 면접 끝: 결과 리포트 ----------
else:
    report = st.session_state.report
    st.divider()
    st.subheader("📊 면접 결과 리포트")

    if "raw" in report:
        st.markdown(report["raw"])
    else:
        # 평균 점수 + 등급 (+ 지난번과 비교)
        history = st.session_state.history
        delta = None
        if len(history) >= 2:
            delta = f"{history[-1]['평균'] - history[-2]['평균']:+d}점 (지난 면접 대비)"
        c1, c2 = st.columns(2)
        c1.metric("평균 점수", f"{report['avg']}점", delta=delta)
        c2.metric("등급", report["grade"])

        # 항목별 점수 막대
        scores = report.get("scores", {})
        for item in SCORE_ITEMS:
            v = scores.get(item, 0)
            v = v if isinstance(v, (int, float)) else 0
            st.progress(min(max(v, 0), 100) / 100, text=f"{item}  {v}점")

        st.info(report.get("summary", ""))

        # 답변 습관
        stats = report.get("stats", {})
        st.markdown("**🗣️ 답변 습관**")
        st.write(f"답변 {stats.get('count', 0)}개 · 평균 {stats.get('avg_len', 0)}자 · "
                 f"평균 {stats.get('avg_sec', 0)}초")
        st.caption(report.get("habit", ""))

        left, right = st.columns(2)
        with left:
            st.markdown("**👍 잘한 점**")
            for x in report.get("good", []):
                st.markdown(f"- {x}")
        with right:
            st.markdown("**🛠️ 보완할 점**")
            for x in report.get("improve", []):
                st.markdown(f"- {x}")

        st.markdown("**📝 질문별 피드백**")
        for i, q in enumerate(report.get("per_question", []), 1):
            with st.expander(f"{i}. {q.get('question', '')}"):
                st.markdown(f"**평가:** {q.get('comment', '')}")
                st.markdown(f"**개선 답변 예시:** {q.get('better_answer', '')}")

        # 여러 번 연습했으면 점수 기록 보여주기
        if len(history) >= 2:
            st.markdown("**📈 이번 접속에서 본 면접 기록**")
            st.table(history)

    st.download_button("📥 리포트 다운로드 (.txt)",
                       data=report_to_text(s, report, st.session_state.messages),
                       file_name="interview_report.txt")
    st.caption("※ AI 피드백은 참고용이에요. 다시 연습하려면 설정을 바꾸고 '면접 시작'을 누르세요.")
