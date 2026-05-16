"""TopDev automation - Selectors verified from DOM inspection."""
import re
import time
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
def _vue_select(page: Page, label_text: str, value: str, field_name: str) -> bool:
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
                # Click cách mép phải 15px, giữa chiều cao
                page.mouse.click(box["x"] + box["width"] - 15, box["y"] + box["height"] / 2)
            else:
                ms.click()
        except Exception:
            ms.click()
        
        time.sleep(0.5)

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
                time.sleep(0.5)  # Đợi dropdown filter cập nhật
        except Exception:
            pass

        # ★ JS Tìm Option An Toàn: Chỉ lùng sục option đang hiển thị
        # Trả về ElementHandle để Playwright tự động click chuẩn xác nhất
        opt_handle = ms.evaluate_handle("""
            (container, args) => {
                const [targetText, shortText] = args;
                const selectors = [
                    'span.multiselect__option',
                    '.multiselect__option',
                    '.multiselect-option',
                    '.multiselect__element span'
                ];
                
                let foundOpt = null;
                const checkOpt = (opt) => {
                    if (opt.offsetWidth === 0 && opt.offsetHeight === 0) return false;
                    const txt = (opt.textContent || '').trim().replace(/\\s+/g, ' ');
                    return (txt === targetText || txt.includes(targetText) || txt.includes(shortText));
                };

                // Ưu tiên tìm trong container của đúng dropdown này
                for (const sel of selectors) {
                    const opts = container.querySelectorAll(sel);
                    for (const opt of opts) {
                        if (checkOpt(opt)) { foundOpt = opt; break; }
                    }
                    if (foundOpt) break;
                }

                // Fallback tìm toàn cục
                if (!foundOpt) {
                    for (const sel of selectors) {
                        const opts = document.querySelectorAll(sel);
                        for (const opt of opts) {
                            if (checkOpt(opt)) { foundOpt = opt; break; }
                        }
                        if (foundOpt) break;
                    }
                }
                return foundOpt;
            }
        """, [value, search_term])

        clicked = False
        opt_element = opt_handle.as_element()
        if opt_element:
            # Dùng Playwright click (tự động dispatch đủ mousedown/mouseup/click)
            # Điều này sửa lỗi Job Category không chọn được do thiếu sự kiện click
            opt_element.click(timeout=3000)
            clicked = True

        if not clicked:
            # Fallback cuối cùng của Playwright
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

        # ★ Đóng dropdown an toàn: gửi Escape vào ô search và click ra ngoài (label) để ép blur
        time.sleep(0.3)
        try:
            search = ms.locator("input.multiselect__input, input[type='text'], input:not([type='hidden'])").first
            search.press("Escape")
        except Exception:
            page.keyboard.press("Escape")
            
        try:
            label.click(force=True)
        except Exception:
            pass
            
        time.sleep(0.2)

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

    # Title — input[name='title'] hoặc placeholder
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

    # Job Category — for='category_id' (Giá trị cứng từ GUIDE)
    _vue_select(page, "Job Category", "Business, Finance", "Job Category")

    # ★ Đợi Role load options (Role phụ thuộc Job Category)
    time.sleep(1.5)

    # Role — for='job_category_id' (Nhiều giá trị cứng từ GUIDE)
    for r in ["Sales / Business Development", "Banking", "Finance / Investment", "Insurance"]:
        _vue_select(page, "Role", r, "Role")

    # Skills — multiselect (Nhiều giá trị cứng từ GUIDE)
    for skill in ["Financial", "Phát triển kinh doanh", "Core Banking"]:
        _vue_select(page, "Skills", skill, "Skills")

    # Level (Nhiều giá trị cứng từ GUIDE)
    for lvl in ["Junior", "Middle", "Senior"]:
        _vue_select(page, "Level", lvl, "Level")

    # Job Type (Giá trị cứng từ GUIDE)
    _vue_select(page, "Job Type", "In Office", "Job Type")

    # Contract type (Giá trị cứng từ GUIDE)
    _vue_select(page, "Contract type", "Fulltime", "Contract type")

    # Working Location
    loc = str(job.get(COL_TINH, "")).strip()
    if loc:
        _vue_select(page, "Working Location", loc, "Working Location")

    # Year of experience — chỉ cần chọn From = Not required
    log_info("Year of experience: Not required")
    try:
        # Tìm section Year of experience → click vào dropdown From (placeholder 'Min')
        yoe_section = page.locator("label").filter(has_text="Year of experience").first
        yoe_parent = yoe_section.locator("xpath=ancestor::div[.//div[contains(@class,'multiselect')]][1]")
        from_ms = yoe_parent.locator("div.multiselect").first
        from_ms.click()
        time.sleep(0.5)
        # Click "Not required" trong dropdown
        from_ms.locator(".multiselect-option, li, span.multiselect__option").filter(has_text="Not required").first.click(timeout=3000)
        time.sleep(0.5)
        # Đóng dropdown
        page.keyboard.press("Escape")
        time.sleep(0.3)
        log_ok("Year of experience From: Not required")
    except Exception as e:
        log_err("Year of experience From", e)
        raise


def step4_job_detail(page: Page, job: dict):
    log_step("Bước 3: Job Description")
    detail = str(job.get(COL_DETAIL, "")).strip()
    if not detail:
        log_skip("Job Detail trống")
        return
    try:
        # TÌM CHÍNH XÁC EDITOR CỦA "JOB DESCRIPTION"
        # Tránh tìm nhầm sang Company Tagline hoặc các ô textarea khác nằm rải rác.
        # Dùng XPath following để chỉ bắt lấy editor ĐẦU TIÊN nằm ngay SAU chữ "Job Description"
        xpath_selector = "xpath=(//*[text()='Job Description' or contains(text(), 'Job Description')]/following::*[contains(@class, 'ql-editor') or @contenteditable='true' or name()='textarea'])[1]"
        
        try:
            editor = page.locator(xpath_selector)
            editor.wait_for(state="visible", timeout=8000)
        except Exception:
            # Nếu XPath fail, thử tìm div contenteditable bất kỳ mà không phải tagline
            editor = page.locator(".ql-editor, div[contenteditable='true']").first
            editor.wait_for(state="visible", timeout=3000)
        
        # Click để focus
        editor.click(force=True)
        time.sleep(0.2)
        
        # Xóa nội dung cũ
        page.keyboard.press("Control+a")
        page.keyboard.press("Backspace")
        time.sleep(0.2)
        
        # Cách 1: Thử insert_text (chèn nhanh qua clipboard event)
        page.keyboard.insert_text(detail)
        time.sleep(0.5)
        
        # Kiểm tra xem text có thực sự được ăn vào editor không
        content = str(editor.text_content() or "").strip()
        if len(content) < 5:
            # Fallback 1: Dùng fill()
            editor.fill(detail)
            time.sleep(0.5)
            content = str(editor.text_content() or "").strip()
            
            if len(content) < 5:
                # Fallback 2: Gõ từng chữ (chậm nhưng chắc chắn kích hoạt 100% key events của trình duyệt)
                editor.click(force=True)
                page.keyboard.press("Control+a")
                page.keyboard.press("Backspace")
                editor.press_sequentially(detail, delay=1)
                
        time.sleep(0.3)
        log_ok("Job Description: %s..." % detail[:60])
    except Exception as e:
        log_err("Job Description", e)
        raise


def step5_responsibilities(page: Page, job: dict):
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
            # Nhấn Enter để thêm tag (an toàn và chuẩn hơn việc đi tìm nút +)
            inp.press("Enter")
            time.sleep(0.2)
            print("    ✅ %s" % item[:70])
    except Exception as e:
        log_err("Responsibilities", e)
        raise


def step6_requirements(page: Page, job: dict):
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
    for item in ["CV screening", "HR Interview"]:
        try:
            # Recruitment process dùng cùng pattern select-container + "+"
            inp = page.locator("input[placeholder*='recruitment'], input[placeholder*='Recruitment']").first
            try:
                inp.wait_for(state="visible", timeout=3000)
            except Exception:
                # Fallback: tìm input trống trong khu vực recruitment
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

    sal_min = str(job.get(COL_SAL_MIN, "")).strip().replace(",", "")
    sal_max = str(job.get(COL_SAL_MAX, "")).strip().replace(",", "")
    log_info("Salary: %s -> %s" % (sal_min, sal_max))
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
            raise
    except Exception as e:
        log_err("Salary", e)
        raise

    # Benefits
    for benefit_name, benefit_desc in BENEFITS_DATA:
        _add_benefit(page, benefit_name, benefit_desc)


def _add_benefit(page: Page, benefit_name: str, description: str):
    log_info("Benefit: %s" % benefit_name)
    try:
        # Tìm section Benefits → Vue multiselect để chọn tên benefit
        heading = page.locator("label, h3, h4").filter(has_text="Benefits").last
        section = heading.locator("xpath=ancestor::div[.//button][1]")
        ms = section.locator("div.multiselect").first
        ms.click()
        time.sleep(0.4)
        search = ms.locator("input.multiselect__input, input[type='text']").first
        search.fill(benefit_name)
        time.sleep(0.6)
        option = ms.locator("span.multiselect__option").filter(has_text=benefit_name).first
        option.click(timeout=5000)
        time.sleep(0.3)
        # Điền mô tả
        desc_inp = section.locator("input[type='text']").last
        desc_inp.fill(description)
        time.sleep(0.2)
        # Bấm +
        btn = section.locator("button").filter(has_text="+").last
        btn.click()
        time.sleep(0.4)
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
