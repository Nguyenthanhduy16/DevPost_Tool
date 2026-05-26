"""TopDev automation - Selectors verified from DOM inspection."""
from difflib import SequenceMatcher
import html
import re
import time
import unicodedata
from playwright.sync_api import Page
from topdev_helpers import (
    log_step, log_ok, log_err, log_info, log_skip, fill_list_section
)

# Mapping cột Excel
COL_TITLE   = "Tên hiển thị trên website MB"
COL_SKILLS  = "Skill tags/Keyword (Xuống dòng để phân cách)"
COL_RESP    = "Mô tả công việc (tiếng Việt) = Responsibility"
COL_REQ     = "Yêu cầu công việc Final"
COL_DETAIL  = "Job Detail "
COL_TINH    = "Tỉnh"
COL_SAL_MIN = "LƯƠNG MIN"
COL_SAL_MAX = "LƯƠNG MAX"
COL_BENEFIT = "Benefit"

DETAIL_COLUMNS = (
    COL_DETAIL,
    "Job Detail",
    "Job Details",
    "Job Description",
    "Job description",
)

DETAIL_LABELS = (
    "Job Detail",
    "Job Details",
    "Job Description",
    "Job description",
)

MULTISELECT_OPTION_SELECTORS = (
    "span.multiselect__option",
    ".multiselect__option",
    ".multiselect-option",
    ".multiselect__element span",
)


# ---------------------------------------------------------------------------
# DATA HELPERS
# ---------------------------------------------------------------------------
def _get_job_value(job: dict, columns: tuple) -> str:
    for col in columns:
        value = str(job.get(col, "")).strip()
        if value:
            return value
    normalized = {str(key).strip().lower(): value for key, value in job.items()}
    for col in columns:
        value = str(normalized.get(col.strip().lower(), "")).strip()
        if value:
            return value
    return ""


def _get_job_detail(job: dict) -> str:
    return _get_job_value(job, DETAIL_COLUMNS)


def _job_list_items(raw_text: str) -> list[str]:
    return [line.strip() for line in str(raw_text).splitlines() if line.strip()]


def _recruitment_rounds() -> list[str]:
    return ["CV screenning", "HR Interview"]


def _salary_input_value(value) -> str:
    text = str(value or "").strip()
    if not text or text.lower() == "nan":
        return ""
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", 1)[0]
    digits = re.sub(r"\D", "", text)
    return digits


def _format_vnd_amount(value: str) -> str:
    digits = _salary_input_value(value)
    if not digits:
        return ""
    return f"{int(digits):,}".replace(",", ".")


def _salary_display_range(sal_min, sal_max) -> str:
    min_display = _format_vnd_amount(sal_min)
    max_display = _format_vnd_amount(sal_max)
    if min_display and max_display:
        return "%s - %s VND" % (min_display, max_display)
    if min_display:
        return "Từ %s VND" % min_display
    if max_display:
        return "Đến %s VND" % max_display
    return ""


def _competitive_salary_description(sal_min, sal_max) -> str:
    min_display = _format_vnd_amount(sal_min)
    max_display = _format_vnd_amount(sal_max)
    if min_display and max_display:
        return "Junior: Từ %s đến %s, theo năng suất lao động" % (min_display, max_display)
    if min_display:
        return "Junior: Từ %s, theo năng suất lao động" % min_display
    if max_display:
        return "Junior: Đến %s, theo năng suất lao động" % max_display
    return ""


def _benefit_default_description(benefit_name: str, sal_min: str = "", sal_max: str = "") -> str:
    if benefit_name == "Competitive Salary":
        salary_description = _competitive_salary_description(sal_min, sal_max)
        if salary_description:
            return salary_description
    return dict(BENEFITS_DATA).get(benefit_name, "")


def _normalize_benefit_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).lower()


def _benefit_match_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", _normalize_benefit_text(text))
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", ascii_text).strip()


def _benefit_keyword_from_text(text: str) -> str:
    raw = str(text or "").strip()
    normalized = _normalize_benefit_text(raw)
    if not normalized:
        return ""

    for keyword, default_desc in BENEFITS_DATA:
        keyword_norm = _normalize_benefit_text(keyword)
        if normalized == keyword_norm:
            return keyword
        if re.match(r"^%s\s*[:\t|]" % re.escape(keyword), raw, flags=re.IGNORECASE):
            return keyword
        if default_desc and normalized == _normalize_benefit_text(default_desc):
            return keyword

    if re.match(r"^(junior|mid-level|professional)\s*:", raw, flags=re.IGNORECASE):
        return "Competitive Salary"

    comparable = _benefit_match_text(raw)
    best_keyword = ""
    best_score = 0.0
    for keyword, default_desc in BENEFITS_DATA:
        if not default_desc:
            continue
        default_comparable = _benefit_match_text(default_desc)
        score = SequenceMatcher(None, comparable, default_comparable).ratio()
        if score > best_score:
            best_keyword = keyword
            best_score = score
    if best_score >= 0.58:
        return best_keyword
    return ""


def _split_benefit_line(line: str) -> tuple[str, str]:
    text = str(line).strip()
    for separator in (":", "\t", "|"):
        if separator in text:
            name, desc = text.split(separator, 1)
            return name.strip(), desc.strip()
    return text, ""


def _get_job_benefits(job: dict, sal_min: str = "", sal_max: str = "") -> list[tuple[str, str]]:
    raw = _get_job_value(job, (COL_BENEFIT, "Benefits", "benefit", "benefits"))
    items = _job_list_items(raw)
    benefits = []
    for item in items:
        mapped_name = _benefit_keyword_from_text(item)
        benefit_name, benefit_desc = _split_benefit_line(item)
        if mapped_name:
            if mapped_name != benefit_name:
                benefit_name = mapped_name
                benefit_desc = item
            else:
                benefit_name = mapped_name
        if not benefit_name:
            continue
        if not benefit_desc:
            benefit_desc = _benefit_default_description(benefit_name, sal_min, sal_max)
        benefits.append((benefit_name, benefit_desc))
    return benefits


def _job_detail_html(text: str) -> str:
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    if not lines:
        return "<p></p>"
    return "".join("<p>%s</p>" % html.escape(line) for line in lines)


def _job_detail_label_xpath() -> str:
    conditions = [
        "contains(normalize-space(), '%s')" % label
        for label in DETAIL_LABELS
    ]
    return (
        "xpath=//*[self::label or self::div or self::span or self::p or self::h3 or self::h4]"
        "[%s]" % " or ".join(conditions)
    )


def _job_detail_textarea_score(meta: dict) -> int:
    text = " ".join(
        str(meta.get(key, "") or "").lower()
        for key in ("name", "id", "placeholder", "aria", "label")
    )
    excluded = ("reason", "comment", "note", "message", "feedback")
    if any(word in text for word in excluded):
        return -100

    score = 0
    for word, weight in (
        ("job detail", 60),
        ("job description", 60),
        ("description", 35),
        ("detail", 35),
        ("responsibility", 20),
        ("content", 10),
    ):
        if word in text:
            score += weight
    return score


def _textarea_diagnostics(items: list) -> str:
    parts = []
    for item in items[:8]:
        attrs = []
        for key in ("index", "name", "id", "placeholder", "aria", "label", "rows"):
            value = str(item.get(key, "") or "").strip()
            if value:
                attrs.append("%s=%s" % (key, value[:40]))
        parts.append("{%s}" % ", ".join(attrs))
    return "; ".join(parts)


def _wait_for_multiselect_option(page: Page, ms, value: str, search_term: str, timeout: int = 2500):
    args = [value, search_term]
    try:
        page.wait_for_function(
            """
            ([targetText, shortText]) => {
                const selectors = %s;
                const checkOpt = (opt) => {
                    if (opt.offsetWidth === 0 && opt.offsetHeight === 0) return false;
                    const txt = (opt.textContent || '').trim().replace(/\\s+/g, ' ');
                    return (txt === targetText || txt.includes(targetText) || txt.includes(shortText));
                };
                for (const sel of selectors) {
                    const opts = document.querySelectorAll(sel);
                    for (const opt of opts) {
                        if (checkOpt(opt)) return true;
                    }
                }
                return false;
            }
            """ % list(MULTISELECT_OPTION_SELECTORS),
            arg=args,
            timeout=timeout,
        )
    except Exception:
        pass

    return ms.evaluate_handle(
        """
        (container, args) => {
            const [targetText, shortText] = args;
            const selectors = %s;
            const checkOpt = (opt) => {
                if (opt.offsetWidth === 0 && opt.offsetHeight === 0) return false;
                const txt = (opt.textContent || '').trim().replace(/\\s+/g, ' ');
                return (txt === targetText || txt.includes(targetText) || txt.includes(shortText));
            };
            for (const root of [container, document]) {
                for (const sel of selectors) {
                    const opts = root.querySelectorAll(sel);
                    for (const opt of opts) {
                        if (checkOpt(opt)) return opt;
                    }
                }
            }
            return null;
        }
        """ % list(MULTISELECT_OPTION_SELECTORS),
        args,
    ).as_element()


def _fill_tinymce_job_detail(page: Page, detail: str) -> bool:
    content_html = _job_detail_html(detail)
    try:
        result = page.evaluate(
            """
            (contentHtml) => {
                const textareas = Array.from(document.querySelectorAll('textarea'));
                const target = textareas.find((el) => {
                    const iframeId = el.id ? `${el.id}_ifr` : '';
                    const nearText = [
                        el.closest('label')?.textContent || '',
                        el.parentElement?.innerText || '',
                        el.parentElement?.parentElement?.innerText || ''
                    ].join(' ');
                    return (
                        el.name === 'content'
                        && iframeId
                        && document.getElementById(iframeId)
                        && /Job\\s+Description/i.test(nearText)
                    );
                }) || textareas.find((el) => {
                    const iframeId = el.id ? `${el.id}_ifr` : '';
                    return el.name === 'content' && iframeId && document.getElementById(iframeId);
                });

                if (!target || !target.id) return { ok: false, reason: 'textarea not found' };

                const editor = window.tinymce?.get?.(target.id) || window.tinyMCE?.get?.(target.id);
                if (editor) {
                    editor.setContent(contentHtml);
                    editor.save();
                    editor.fire('change');
                    return { ok: true, method: 'tinymce-api', id: target.id };
                }

                const iframe = document.getElementById(`${target.id}_ifr`);
                const doc = iframe?.contentDocument;
                const body = doc?.body;
                if (!body) return { ok: false, reason: 'iframe body not found', id: target.id };

                body.innerHTML = contentHtml;
                body.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText' }));
                body.dispatchEvent(new Event('change', { bubbles: true }));
                target.value = contentHtml;
                target.dispatchEvent(new Event('input', { bubbles: true }));
                target.dispatchEvent(new Event('change', { bubbles: true }));
                return { ok: true, method: 'iframe+textarea', id: target.id };
            }
            """,
            content_html,
        )
        if result and result.get("ok"):
            log_info("TinyMCE Job Description: %s" % result.get("method", "filled"))
            return True
        log_info("TinyMCE Job Description skipped: %s" % (result or {}).get("reason", "unknown"))
        return False
    except Exception as e:
        log_info("TinyMCE Job Description skipped: %s" % e)
        return False


def _add_text_list_item(page: Page, label_text: str, placeholder: str, item: str, timeout: int = 8000):
    label = page.locator("label").filter(has_text=label_text).first
    label.scroll_into_view_if_needed(timeout=timeout)
    section = label.locator("xpath=ancestor::div[.//input and .//button][1]")
    inp = section.locator("input[placeholder='%s']" % placeholder).first
    inp.wait_for(state="visible", timeout=timeout)
    inp.click()
    inp.fill("")
    inp.fill(item)

    add_button = section.locator("button").filter(has_text="+").last
    if add_button.count() == 0:
        add_button = section.locator("button").last
    add_button.click(timeout=timeout)

    try:
        page.wait_for_function(
            "(input) => !input.value || input.value.trim() === ''",
            arg=inp.element_handle(timeout=1000),
            timeout=2500,
        )
    except Exception:
        if str(inp.input_value(timeout=1000)).strip() == item.strip():
            raise Exception("Sau khi bấm +, input '%s' vẫn chưa được thêm/clear" % placeholder)
    page.keyboard.press("Escape")
    page.keyboard.press("Escape")
    page.mouse.click(20, 20)


def _fill_text_list_section(page: Page, label_text: str, placeholder: str, raw_text: str, section_name: str):
    items = _job_list_items(raw_text)
    if not items:
        log_skip("%s trống" % section_name)
        return
    log_info("Điền %d items" % len(items))
    for item in items:
        _add_text_list_item(page, label_text, placeholder, item)
        print("    ✅ %s" % item[:70])
    page.keyboard.press("Escape")
    page.mouse.click(20, 20)


def _click_section_plus(page: Page, label_text: str, timeout: int = 5000):
    label = page.locator("label").filter(has_text=label_text).first
    section = label.locator("xpath=ancestor::div[.//button][1]")
    btn = section.locator("button").filter(has_text="+").last
    if btn.count() == 0:
        btn = section.locator("button").last
    btn.click(timeout=timeout)


def _fill_salary_range(page: Page, sal_min: str, sal_max: str):
    salary_label = page.locator("label").filter(has_text="Salary").first
    salary_label.scroll_into_view_if_needed(timeout=5000)
    section = salary_label.locator("xpath=ancestor::div[.//input][1]")
    inputs = section.locator("input:not([type='checkbox']):not([type='radio']):not([type='hidden'])")
    n = inputs.count()
    if n >= 2:
        inputs.first.fill(sal_min)
        inputs.last.fill(sal_max)
        log_ok("Salary: %s → %s" % (sal_min, sal_max))
    elif n == 1:
        inputs.first.fill(sal_min)
        log_ok("Salary min: %s (chỉ tìm được 1 ô)" % sal_min)
    else:
        raise Exception("No salary input found in Salary section")


# ---------------------------------------------------------------------------
# EDITOR FINDER
# ---------------------------------------------------------------------------
def _find_job_detail_editor(page: Page):
    """
    Tìm vùng soạn thảo Job Description theo thứ tự ưu tiên:
    1. .ql-editor visible (Quill) — chờ tích cực tới 10 giây
    2. [contenteditable='true'] visible gần label Job Description
    3. textarea visible gần label (loại trừ không liên quan)

    Dùng wait_for_selector để CHỜ element xuất hiện trong DOM.
    Raise ValueError kèm chẩn đoán nếu không tìm được.
    """
    # ── Ưu tiên 1: Chờ .ql-editor xuất hiện (timeout 10s) ───────────────────
    try:
        page.wait_for_selector(".ql-editor", state="visible", timeout=10000)
        count = page.locator(".ql-editor").count()
        for i in range(count):
            ql = page.locator(".ql-editor").nth(i)
            try:
                if ql.is_visible(timeout=300):
                    return ql, "quill"
            except Exception:
                pass
    except Exception:
        pass

    # ── Ưu tiên 2: contenteditable visible gần label Job Description ──────────
    for label in DETAIL_LABELS:
        try:
            loc = page.locator(
                "xpath=//*[self::label or self::div or self::span or self::p or self::h3 or self::h4]"
                "[contains(normalize-space(), '%s')]/following::*[@contenteditable='true'][1]" % label
            )
            loc.first.wait_for(state="visible", timeout=5000)
            return loc.first, "contenteditable"
        except Exception:
            pass

    # ── Ưu tiên 3: textarea visible gần label (loại trừ không liên quan) ─────
    EXCLUDED = ("reason", "comment", "note", "message", "feedback")
    for label in DETAIL_LABELS:
        try:
            loc = page.locator(
                "xpath=//*[contains(normalize-space(), '%s')]/following::textarea[1]" % label
            )
            if loc.count() > 0:
                el = loc.first
                el_id = str(el.get_attribute("id") or "").lower()
                el_name = str(el.get_attribute("name") or "").lower()
                if any(x in el_id or x in el_name for x in EXCLUDED):
                    continue
                el.wait_for(state="visible", timeout=5000)
                return el, "textarea"
        except Exception:
            pass

    # ── Không tìm thấy → raise kèm chẩn đoán ────────────────────────────────
    try:
        candidates = page.locator("textarea:visible").evaluate_all(
            """
            (nodes) => nodes.map((el, index) => {
                const label = el.closest('label')?.textContent
                    || el.parentElement?.querySelector('label')?.textContent
                    || '';
                return {
                    index,
                    name: el.getAttribute('name') || '',
                    id: el.getAttribute('id') || '',
                    placeholder: el.getAttribute('placeholder') || '',
                    aria: el.getAttribute('aria-label') || '',
                    label,
                    rows: Number(el.getAttribute('rows') || 0)
                };
            })
            """
        )
        ranked = [
            (_job_detail_textarea_score(meta), meta)
            for meta in candidates
        ]
        ranked.sort(key=lambda item: (item[0], item[1].get("rows", 0)), reverse=True)
        if ranked and ranked[0][0] > 0:
            index = int(ranked[0][1]["index"])
            return page.locator("textarea:visible").nth(index), "textarea"
    except Exception:
        pass

    n_ql = page.locator(".ql-editor").count()
    n_ce = page.locator("[contenteditable='true']").count()
    n_ta = page.locator("textarea").count()
    try:
        textarea_details = page.locator("textarea").evaluate_all(
            """
            (nodes) => nodes.map((el, index) => ({
                index,
                name: el.getAttribute('name') || '',
                id: el.getAttribute('id') || '',
                placeholder: el.getAttribute('placeholder') || '',
                aria: el.getAttribute('aria-label') || '',
                rows: el.getAttribute('rows') || ''
            }))
            """
        )
    except Exception:
        textarea_details = []
    raise ValueError(
        "Không tìm thấy Job Description editor. "
        "Chẩn đoán: .ql-editor=%d, contenteditable=%d, textarea=%d. "
        "Trang có thể chưa load đủ hoặc cần scroll." % (n_ql, n_ce, n_ta)
    )


# ---------------------------------------------------------------------------
# BENEFITS DATA
# ---------------------------------------------------------------------------
BENEFITS_DATA = [
    ("Annual Bonuses",        "Thưởng dịp lễ tết, thưởng thành tích gắn với hiệu suất công việc/kết quả kinh doanh"),
    ("Social events",         "Đãi ngộ gắn kết (Tặng quà sinh nhật, quà Tết Nguyên đán, đãi ngộ thâm niên.....)"),
    ("Health care",           "Bảo hiểm chăm sóc sức khỏe cho CBNV/người thân với các đặc quyền độc đáo"),
    ("Travel opportunities and global exposure", "Du lịch/nghỉ dưỡng hàng năm trong nước & nước ngoài"),
    ("Employee discounts",    "Được tư vấn, hỗ trợ tài chính & trải nghiệm các sản phẩm tài chính cá nhân, bảo hiểm..."),
    ("Career Growth Opportunities", "Lộ trình thăng tiến rõ ràng, cơ hội phát triển với các nhóm nghề nghiệp tại Ngân hàng"),
    ("Professional Development",    'Được dẫn dắt bởi Lãnh đạo danh tiếng, được đồng hành và "Learning on Jobs" cùng các chương trình phát triển chuyên môn'),
    ("Learning opportunities", "Tiếp cận các chương trình đào tạo theo chuẩn quốc tế, được trải nghiệm, tích lũy kinh nghiệm"),
    ("Working environment",   "Môi trường làm việc trẻ trung, chuyên nghiệp, ứng dụng toàn diện các phương pháp làm việc hiện đại"),
    ("Competitive Salary",    "Lương cạnh tranh theo năng suất lao động, thưởng hiệu suất"),
]


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
def _vue_select(
    page: Page,
    label_text: str,
    value: str,
    field_name: str,
    option_timeout: int = 3000,
    filter_wait: float = 0.2,
    close_wait: float = 0.05,
) -> bool:
    """Chọn 1 giá trị trong Vue Multiselect bằng cách tìm qua label text."""
    value = str(value).strip()
    if not value:
        log_skip(field_name)
        return False
    log_info("%s: %s" % (field_name, value))
    try:
        # Tìm label → đi lên cha → tìm div.multiselect bên trong
        label = page.locator("label").filter(has_text=label_text).first
        parent = label.locator("xpath=ancestor::div[.//div[contains(@class,'multiselect')]][1]")
        ms = parent.locator("div.multiselect").first
        ms.wait_for(state="visible", timeout=5000)

        # ★ Mở dropdown an toàn: Click vào bên phải của container (chỗ mũi tên)
        # để KHÔNG BAO GIỜ trúng các nút [×] của tag đã chọn trước đó.
        try:
            box = ms.bounding_box()
            if box:
                page.mouse.click(box["x"] + box["width"] - 15, box["y"] + box["height"] / 2)
            else:
                ms.click()
        except Exception:
            ms.click()

        time.sleep(filter_wait)

        # Gõ tìm kiếm: dùng keyword ngắn (trước dấu /, ,, -) để bộ lọc dễ match nhất
        search_term = value.replace(",", "/").replace("-", "/").split("/")[0].strip()
        try:
            search = ms.locator("input.multiselect__input, input[type='text'], input:not([type='hidden'])").first
            if search.is_visible(timeout=800) and search.is_editable():
                # Dùng fill để nhập nhanh (nhanh hơn press_sequentially)
                # KHÔNG dùng Backspace ở đây vì Backspace khi input trống sẽ xoá tag đã chọn!
                search.fill(search_term)
                # Kích hoạt sự kiện input/keyup cho Vue
                search.press("Space")
                search.press("Backspace")
                time.sleep(filter_wait)
        except Exception:
            pass

        clicked = False
        opt_element = _wait_for_multiselect_option(page, ms, value, search_term, timeout=option_timeout)
        if opt_element:
            opt_element.click(timeout=3000)
            clicked = True

        if not clicked:
            try:
                option = page.locator(
                    "span.multiselect__option:visible, .multiselect-option:visible"
                ).filter(has_text=search_term).first
                option.click(timeout=3000)
                clicked = True
            except Exception:
                pass

        if not clicked:
            raise Exception("Không tìm thấy option '%s' (hoặc '%s') để click" % (value, search_term))

        # Đóng dropdown để field kế tiếp không bị overlay chặn.
        try:
            search = ms.locator("input.multiselect__input, input[type='text'], input:not([type='hidden'])").first
            search.press("Escape")
        except Exception:
            page.keyboard.press("Escape")
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        try:
            page.mouse.click(20, 20)
        except Exception:
            pass

        time.sleep(close_wait)
        log_ok("%s: %s" % (field_name, value))
        return True
    except Exception as e:
        log_err("%s: %s" % (field_name, value), e)
        raise


def _vue_select_multi(page: Page, label_text: str, values: list, field_name: str):
    """Chọn nhiều giá trị trong Vue Multiselect (Skills)."""
    for v in values:
        _vue_select(page, label_text, v, field_name)


# ---------------------------------------------------------------------------
# STEPS
# ---------------------------------------------------------------------------
def step1_navigate(page: Page):
    log_step("Bước 1: Điều hướng trang tạo job")
    try:
        page.goto("https://dash.topdev.vn/jobs/create", timeout=60000)
        page.wait_for_load_state("networkidle", timeout=30000)
        time.sleep(2)
        log_ok("Đã vào trang tạo job")
    except Exception as e:
        log_err("Không vào được trang tạo job", e)
        raise


def step2_package(page: Page):
    log_step("Bước 2a: Chọn Package")
    try:
        pkg = page.locator("label").filter(has_text="Top Job Unlimited - MBBank").first
        pkg.wait_for(state="visible", timeout=8000)
        pkg.click()
        time.sleep(0.5)
        log_ok("Package: Top Job Unlimited - MBBank")
    except Exception as e:
        try:
            page.locator("table input[type='radio']").first.click()
            log_ok("Package: gói đầu tiên")
        except Exception as e2:
            log_err("Package", e2)
            raise


def step3_basic_info(page: Page, job: dict):
    title = str(job.get(COL_TITLE, "")).strip()
    log_step("Bước 2b: Thông tin cơ bản", title)

    # Title
    if title:
        try:
            inp = page.locator("input[name='title']").first
            inp.wait_for(state="visible", timeout=5000)
            inp.click()
            inp.fill(title)
            log_ok("Title: %s" % title[:60])
        except Exception as e:
            log_err("Title", e)
            raise

    # Job Category (giá trị cứng từ GUIDE)
    _vue_select(page, "Job Category", "Business, Finance", "Job Category")

    # Role (nhiều giá trị cứng từ GUIDE)
    for r in ["Sales / Business Development", "Banking", "Finance / Investment", "Insurance"]:
        _vue_select(page, "Role", r, "Role")

    # Skills
    for skill in ["Financial", "Phát triển kinh doanh", "Core Banking"]:
        _vue_select(page, "Skills", skill, "Skills")

    # Level
    for lvl in ["Junior", "Middle", "Senior"]:
        _vue_select(page, "Level", lvl, "Level")

    # Job Type
    _vue_select(page, "Job Type", "In Office", "Job Type")

    # Contract type
    _vue_select(page, "Contract type", "Fulltime", "Contract type")

    # Working Location
    loc = str(job.get(COL_TINH, "")).strip()
    if loc:
        _vue_select(
            page,
            "Working Location",
            loc,
            "Working Location",
            option_timeout=1800,
            filter_wait=0.1,
            close_wait=0.02,
        )

    # Year of experience — chỉ cần chọn From = Not required
    _vue_select(
        page,
        "Year of experience",
        "Not required",
        "Year of experience From",
        option_timeout=1800,
        filter_wait=0.1,
        close_wait=0.02,
    )


def step4_job_detail(page: Page, job: dict):
    """
    Điền nội dung vào ô Job Description (Rich Text / Quill editor).

    Chiến lược:
    0. Scroll tới section để trigger lazy-mount của Quill
    1. Quill JS API  – dùng Quill instance để setContents (reactive 100%)
    2. Clipboard paste – execCommand('insertText') trigger đầy đủ events
    3. Fallback – press_sequentially từng ký tự
    """
    log_step("Bước 3: Job Description")
    detail = _get_job_detail(job)
    if not detail:
        log_skip("Job Detail trống")
        return

    # ── Bước 0: Scroll tới label để Quill được lazy-mount ────────────────────
    # TopDev lazy-render Quill: .ql-editor chỉ xuất hiện khi section vào viewport
    log_info("Scroll tới section Job Description...")
    scrolled = False
    for label in DETAIL_LABELS:
        try:
            lbl_loc = page.locator(
                "xpath=//*[self::label or self::div or self::span or self::p "
                "or self::h3 or self::h4 or self::legend]"
                "[contains(normalize-space(), '%s')]" % label
            )
            if lbl_loc.count() > 0:
                lbl_loc.first.scroll_into_view_if_needed(timeout=3000)
                time.sleep(1.5)  # Chờ Quill khởi tạo sau khi vào viewport
                scrolled = True
                break
        except Exception:
            pass
    if not scrolled:
        page.evaluate("window.scrollBy(0, 700)")
        time.sleep(1.5)

    if _fill_tinymce_job_detail(page, detail):
        log_ok("Job Description (TinyMCE): %s..." % detail[:60])
        return

    # ── Tìm editor (sau khi đã scroll) ───────────────────────────────────────
    try:
        editor, editor_type = _find_job_detail_editor(page)
        editor.scroll_into_view_if_needed(timeout=3000)
        editor.wait_for(state="visible", timeout=5000)
        log_info("Editor type: %s" % editor_type)
    except Exception as e:
        log_err("Không tìm thấy Job Description editor", e)
        raise

    # ── Trường hợp textarea thông thường ─────────────────────────────────────
    if editor_type == "textarea":
        try:
            editor.click()
            editor.fill(detail)
            log_ok("Job Description (textarea): %s..." % detail[:60])
            return
        except Exception as e:
            log_err("Job Description textarea", e)
            raise

    # ── Tầng 1: Quill JS API trực tiếp (đảm bảo Vue reactive) ───────────────
    filled = editor.evaluate("""
        (editorEl, text) => {
            let el = editorEl;
            let quill = null;
            for (let i = 0; i < 6; i++) {
                if (!el) break;
                quill = el.__quill || el._quill;
                if (quill) break;
                el = el.parentElement;
            }
            if (!quill && window.Quill) {
                const containers = document.querySelectorAll('.ql-container');
                for (const c of containers) {
                    if (c.__quill) { quill = c.__quill; break; }
                }
            }
            if (!quill) return false;
            const lines = String(text).split(/\\n/);
            const ops = [];
            for (let i = 0; i < lines.length; i++) {
                if (lines[i]) ops.push({ insert: lines[i] });
                ops.push({ insert: '\\n' });
            }
            quill.setContents({ ops });
            quill.root.dispatchEvent(new Event('change', { bubbles: true }));
            return true;
        }
    """, detail)

    if filled:
        time.sleep(0.3)
        log_ok("Job Description (Quill API): %s..." % detail[:60])
        return

    log_info("Quill API không khả dụng, thử Clipboard paste...")

    # ── Tầng 2: execCommand('insertText') ────────────────────────────────────
    pasted = editor.evaluate("""
        (editorEl, text) => {
            editorEl.focus();
            document.execCommand('selectAll', false, null);
            document.execCommand('delete', false, null);
            const success = document.execCommand('insertText', false, text);
            if (!success) {
                editorEl.textContent = text;
                editorEl.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
                editorEl.dispatchEvent(new Event('change', { bubbles: true }));
            }
            return editorEl.textContent.length > 0;
        }
    """, detail)

    if pasted:
        time.sleep(0.3)
        editor.press("End")
        log_ok("Job Description (Clipboard): %s..." % detail[:60])
        return

    log_info("Clipboard paste thất bại, dùng press_sequentially (chậm)...")

    # ── Tầng 3: Fallback cuối – gõ từng ký tự ────────────────────────────────
    try:
        editor.click(force=True)
        page.keyboard.press("Control+a")
        page.keyboard.press("Backspace")
        lines = detail.split("\n")
        for i, line in enumerate(lines):
            if line:
                editor.press_sequentially(line, delay=2)
            if i < len(lines) - 1:
                page.keyboard.press("Enter")
        time.sleep(0.3)
        log_ok("Job Description (type): %s..." % detail[:60])
    except Exception as e:
        log_err("Job Description", e)
        raise


def step5_responsibilities(page: Page, job: dict):
    try:
        log_step("Bước 4: Responsibilities")
        _fill_text_list_section(page, "Responsibilities", "Input your responsibilities", job.get(COL_RESP, ""), "Responsibilities")
        return
    except Exception as e:
        log_err("Responsibilities", e)
        raise
    log_step("Bước 4: Responsibilities")
    raw = job.get(COL_RESP, "")
    items = [l.strip() for l in str(raw).split("\n") if l.strip()]
    if not items:
        log_skip("Responsibilities trống")
        return
    log_info("Điền %d items" % len(items))
    try:
        inp = page.locator("input[placeholder='Input your responsibilities']").first
        inp.wait_for(state="visible", timeout=8000)
        for item in items:
            inp.click()
            inp.fill(item)
            time.sleep(0.2)
            inp.press("Enter")
            time.sleep(0.2)
            print("    ✅ %s" % item[:70])
    except Exception as e:
        log_err("Responsibilities", e)
        raise


def step6_requirements(page: Page, job: dict):
    try:
        log_step("Bước 5: Requirements")
        _fill_text_list_section(page, "Requirements", "Input your requirements", job.get(COL_REQ, ""), "Requirements")
        return
    except Exception as e:
        log_err("Requirements", e)
        raise
    log_step("Bước 5: Requirements")
    raw = job.get(COL_REQ, "")
    items = [l.strip() for l in str(raw).split("\n") if l.strip()]
    if not items:
        log_skip("Requirements trống")
        return
    log_info("Điền %d items" % len(items))
    try:
        inp = page.locator("input[placeholder='Input your requirements']").first
        inp.wait_for(state="visible", timeout=8000)
        for item in items:
            inp.click()
            inp.fill(item)
            time.sleep(0.2)
            inp.press("Enter")
            time.sleep(0.2)
            print("    ✅ %s" % item[:70])
    except Exception as e:
        log_err("Requirements", e)
        raise


def step7_recruitment(page: Page):
    log_step("Bước 6: Recruitment Process")
    for index, item in enumerate(_recruitment_rounds(), start=1):
        try:
            _vue_select(page, "Recruitment process", item, "Recruitment Round %d" % index)
            _click_section_plus(page, "Recruitment process")
            page.keyboard.press("Escape")
            page.mouse.click(20, 20)
            time.sleep(0.2)
            log_ok("Recruitment Round %d: %s" % (index, item))
        except Exception as e:
            log_err("Recruitment Round %d: %s" % (index, item), e)
            raise
    return
    log_step("Bước 6: Recruitment Process")
    for item in ["CV screening", "HR Interview"]:
        try:
            inp = page.locator("input[placeholder*='recruitment'], input[placeholder*='Recruitment']").first
            try:
                inp.wait_for(state="visible", timeout=3000)
            except Exception:
                inp = page.locator("text=Recruitment process").locator(
                    "xpath=ancestor::div[.//input][1]"
                ).locator("input").first
                inp.wait_for(state="visible", timeout=3000)
            inp.click()
            inp.fill(item)
            time.sleep(0.3)
            inp.press("Enter")
            time.sleep(0.3)
            log_ok("Recruitment: %s" % item)
        except Exception as e:
            log_err("Recruitment: %s" % item, e)
            raise


def step8_education(page: Page):
    log_step("Bước 7: Education")
    _vue_select(page, "Degree", "Bachelor", "Degree")
    for major in ["Finance", "Business"]:
        _vue_select(page, "Major", major, "Major/" + major)


def step9_salary_benefits(page: Page, job: dict):
    log_step("Bước 8: Salary & Benefits")

    sal_min = _salary_input_value(job.get(COL_SAL_MIN, ""))
    sal_max = _salary_input_value(job.get(COL_SAL_MAX, ""))
    log_info("Salary: %s -> %s" % (sal_min, sal_max))
    try:
        _fill_salary_range(page, sal_min, sal_max)
    except Exception as e:
        log_err("Salary", e)
        raise
    benefits = _get_job_benefits(job, sal_min, sal_max)
    if not benefits:
        log_skip("Benefits trống")
        return
    previous_benefit_name = ""
    for benefit_name, benefit_desc in benefits:
        is_repeated_previous_benefit = benefit_name == previous_benefit_name
        _add_benefit(
            page,
            benefit_name,
            benefit_desc,
            require_commit=is_repeated_previous_benefit,
            select_twice=is_repeated_previous_benefit,
        )
        previous_benefit_name = benefit_name
    return
    try:
        sal_inputs = page.locator("input[type='number'], input[type='text'][name*='salary'], input[name*='sal']")
        n = sal_inputs.count()
        if n >= 2:
            sal_inputs.first.fill(sal_min)
            sal_inputs.last.fill(sal_max)
            log_ok("Salary: %s → %s" % (sal_min, sal_max))
        elif n == 1:
            sal_inputs.first.fill(sal_min)
            log_ok("Salary min: %s (chỉ tìm được 1 ô)" % sal_min)
        else:
            log_err("Salary: không tìm thấy input")
            raise Exception("No salary input found")
    except Exception as e:
        log_err("Salary", e)
        raise

    salary_range = _salary_display_range(sal_min, sal_max)
    for benefit_name, benefit_desc in BENEFITS_DATA:
        if benefit_name == "Competitive Salary" and salary_range:
            benefit_desc = "Lương cạnh tranh %s, theo năng suất lao động" % salary_range
        _add_benefit(page, benefit_name, benefit_desc)


def _add_benefit(
    page: Page,
    benefit_name: str,
    description: str,
    open_wait: float = 0.1,
    filter_wait: float = 0.15,
    after_select_wait: float = 0.05,
    after_fill_wait: float = 0.05,
    commit_timeout: float = 0.6,
    require_commit: bool = False,
    select_twice: bool = False,
):
    log_info("Benefit: %s" % benefit_name)
    try:
        heading = page.locator("label, h3, h4").filter(has_text="Benefits").last
        section = heading.locator("xpath=ancestor::div[.//button][1]")
        ms = section.locator("div.multiselect").last
        ms.click()
        time.sleep(open_wait)
        search = ms.locator("input.multiselect__input, input[type='text']").first
        def reset_benefit_search():
            def current_search_value():
                try:
                    return str(search.input_value(timeout=300)).strip()
                except Exception:
                    return ""

            def clear_with_keyboard():
                try:
                    search.fill("")
                    search.press("Control+A")
                    search.press("Backspace")
                    search.press("Delete")
                    search.press("Escape")
                except Exception:
                    try:
                        page.keyboard.press("Escape")
                    except Exception:
                        pass

            clear_selectors = (
                ".multiselect__clear",
                ".multiselect__tag-icon",
                "[class*='clear']",
                "[class*='remove']",
                "button[aria-label*='clear' i]",
                "button[title*='clear' i]",
            )
            for clear_selector in clear_selectors:
                try:
                    clear_buttons = ms.locator(clear_selector)
                    if clear_buttons.count() > 0:
                        clear_buttons.first.click(timeout=500)
                        time.sleep(0.05)
                        if not current_search_value():
                            return
                except Exception:
                    pass
            clear_with_keyboard()

        search_term = benefit_name.replace(",", "/").replace("-", "/").split("/")[0].strip()
        reset_benefit_search()
        search.fill(benefit_name)
        try:
            search.press("Space")
            search.press("Backspace")
        except Exception:
            pass
        time.sleep(filter_wait)
        option = _wait_for_multiselect_option(page, ms, benefit_name, search_term, timeout=1800)
        if not option:
            raise Exception("Không tìm thấy benefit option '%s'" % benefit_name)
        desc_selector = "xpath=.//input[@type='text' and not(ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' multiselect ')])]"
        desc_inputs = section.locator(desc_selector)
        desc_count_before = desc_inputs.count()
        option.click(timeout=5000)
        if select_twice:
            time.sleep(after_select_wait)
            ms.click()
            time.sleep(open_wait)
            search.fill(benefit_name)
            try:
                search.press("Space")
                search.press("Backspace")
            except Exception:
                pass
            time.sleep(filter_wait)
            option = _wait_for_multiselect_option(page, ms, benefit_name, search_term, timeout=1800)
            if not option:
                raise Exception("Không tìm thấy benefit option '%s'" % benefit_name)
            option.click(timeout=5000)
        time.sleep(after_select_wait)
        desc_inputs = section.locator(desc_selector)
        deadline = time.time() + commit_timeout
        expected_desc_count = desc_count_before + 1
        while desc_inputs.count() < expected_desc_count and time.time() < deadline:
            time.sleep(0.05)
            desc_inputs = section.locator(desc_selector)
        if desc_inputs.count() < expected_desc_count:
            log_info(
                "Benefit '%s': chưa thấy ô mô tả mới, dùng ô mô tả cuối hiện có (%d -> %d)"
                % (benefit_name, desc_count_before, desc_inputs.count())
            )
        desc_inp = desc_inputs.last
        desc_count_before_add = desc_inputs.count()
        desc_inp.fill(description)
        try:
            desc_inp.press("Tab")
        except Exception:
            pass
        time.sleep(after_fill_wait)
        empty_select_selector = "input[placeholder='Select benefit'], input[placeholder*='benefit'], .multiselect__placeholder"
        try:
            empty_select_count_before_add = section.locator(empty_select_selector).count()
        except Exception:
            empty_select_count_before_add = 0
        btn = section.locator("button").filter(has_text="+")
        if btn.count() == 0:
            btn = section.locator("button")
        btn = btn.last

        def entry_committed():
            desc_inputs = section.locator(desc_selector)
            if desc_inputs.count() > desc_count_before_add:
                return True
            try:
                if str(desc_inp.input_value(timeout=300)).strip() != str(description).strip():
                    return True
            except Exception:
                pass
            try:
                return section.locator(empty_select_selector).count() > empty_select_count_before_add
            except Exception:
                return False

        for attempt in range(2):
            btn.click(timeout=5000)
            deadline = time.time() + commit_timeout
            while time.time() < deadline:
                if entry_committed():
                    break
                time.sleep(0.05)
            if entry_committed():
                break
            try:
                desc_inp.press("Tab")
            except Exception:
                pass
        if not entry_committed():
            message = "Benefit '%s' chưa được thêm sau khi bấm +" % benefit_name
            if require_commit:
                raise Exception(message)
            log_info("%s, tiếp tục dòng kế tiếp" % message)
        reset_benefit_search()
        log_ok("Benefit: %s" % benefit_name)
    except Exception as e:
        log_err("Benefit: %s" % benefit_name, e)
        raise


def step10_design(page: Page):
    log_step("Bước 9: Design")
    # Màu xanh đầu tiên
    try:
        page.locator("[class*='color'] input[type='radio'], [class*='color-item']").first.click()
        log_ok("Màu: xanh dương đầu tiên")
        time.sleep(0.3)
    except Exception as e:
        log_err("Chọn màu", e)
        raise
    # Banner 2
    try:
        banner_section = page.locator("text=Choose banner").locator(
            "xpath=ancestor::div[.//input[@type='radio']][1]"
        )
        radios = banner_section.locator("input[type='radio']")
        if radios.count() >= 2:
            radios.nth(1).check()
            log_ok("Banner: Banner 2")
        time.sleep(0.3)
    except Exception as e:
        log_err("Banner 2", e)
        raise
    # Template 1
    try:
        tmpl_section = page.locator("text=Choose template").locator(
            "xpath=ancestor::div[.//input[@type='radio']][1]"
        )
        tmpl_section.locator("input[type='radio']").first.check()
        log_ok("Template: Template 1")
        time.sleep(0.3)
    except Exception as e:
        log_err("Template 1", e)
        raise


def step11_save_draft(page: Page):
    log_step("Bước 10: Save Draft")
    try:
        btn = page.get_by_role("button", name="Save Draft").first
        btn.wait_for(state="visible", timeout=8000)
        btn.click()
        page.wait_for_load_state("networkidle", timeout=20000)
        log_ok("Đã lưu Draft! 🎉")
    except Exception as e:
        try:
            page.locator("button").filter(has_text="Save Draft").first.click()
            page.wait_for_load_state("networkidle", timeout=20000)
            log_ok("Đã lưu Draft! 🎉")
        except Exception:
            log_err("Save Draft", e)
            raise


# ---------------------------------------------------------------------------
def post_single_job(page: Page, job: dict) -> bool:
    title = job.get(COL_TITLE, "Unknown")
    print("\n" + "═"*55)
    print("🚀 Bắt đầu đăng tin: %s" % title)
    print("═"*55)
    try:
        step1_navigate(page)
        step2_package(page)
        step3_basic_info(page, job)
        step4_job_detail(page, job)
        step5_responsibilities(page, job)
        step6_requirements(page, job)
        step7_recruitment(page)
        step8_education(page)
        step9_salary_benefits(page, job)
        step10_design(page)
        step11_save_draft(page)
        print("\n🎉 HOÀN THÀNH: %s" % title)
        return True
    except Exception as e:
        print("\n💥 LỖI '%s': %s" % (title, e))
        print("⏸️ Trình duyệt đang được giữ mở để bạn kiểm tra (F12).")
        print("🛑 Khi kiểm tra xong, hãy nhấn nút STOP (Interrupt) trên Jupyter Notebook để tắt an toàn.")
        page.pause()
        return False
