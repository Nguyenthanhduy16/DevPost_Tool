import unittest
import inspect
from unittest.mock import patch

from topdev_automation import (
    BENEFITS_DATA,
    _add_benefit,
    _fill_salary_range,
    _get_job_benefits,
    _get_job_detail,
    _job_detail_html,
    _job_detail_label_xpath,
    _job_detail_textarea_score,
    _job_list_items,
    _salary_display_range,
    _salary_input_value,
    _recruitment_rounds,
    step3_basic_info,
    step9_salary_benefits,
    _vue_select,
    _wait_for_multiselect_option,
)


class _FakeHandle:
    def __init__(self, element):
        self._element = element

    def as_element(self):
        return self._element


class _FakeMultiselect:
    def __init__(self, element):
        self.wait_args = None
        self.evaluate_args = None
        self._element = element

    def evaluate_handle(self, script, args):
        self.evaluate_args = (script, args)
        return _FakeHandle(self._element)


class _FakePage:
    def __init__(self):
        self.wait_args = None

    def wait_for_function(self, script, arg=None, timeout=None):
        self.wait_args = (script, arg, timeout)
        return True


class _FakeInput:
    def __init__(self):
        self.value = None

    def fill(self, value):
        self.value = value


class _FakeInputs:
    def __init__(self, items):
        self.items = items

    def count(self):
        return len(self.items)

    @property
    def first(self):
        return self.items[0]

    @property
    def last(self):
        return self.items[-1]


class _FakeSection:
    def __init__(self):
        self.inputs = [_FakeInput(), _FakeInput()]
        self.last_selector = None

    def locator(self, selector):
        self.last_selector = selector
        if selector == "input:not([type='checkbox']):not([type='radio']):not([type='hidden'])":
            return _FakeInputs(self.inputs)
        raise AssertionError(selector)


class _FakeLabel:
    def __init__(self, section):
        self.section = section

    def scroll_into_view_if_needed(self, timeout=None):
        return None

    def locator(self, selector):
        return self.section


class _FakeLabels:
    def __init__(self, section):
        self.section = section

    def filter(self, has_text=None):
        return self

    @property
    def first(self):
        return _FakeLabel(self.section)


class _FakeSalaryPage:
    def __init__(self):
        self.section = _FakeSection()

    def locator(self, selector):
        if selector == "label":
            return _FakeLabels(self.section)
        raise AssertionError(selector)


class _FakeChainLocator:
    def __init__(self):
        self.filled = []
        self.clicks = 0
        self.value = ""

    def filter(self, has_text=None):
        return self

    @property
    def first(self):
        return self

    @property
    def last(self):
        return self

    def locator(self, selector):
        return self

    def click(self, timeout=None):
        self.clicks += 1
        self.value = ""

    def fill(self, value):
        self.filled.append(value)
        self.value = value

    def input_value(self, timeout=None):
        return self.value

    def count(self):
        return 1


class _FakeBenefitPage:
    def __init__(self):
        self.root = _FakeChainLocator()

    def locator(self, selector):
        return self.root


class _FakeOption:
    def __init__(self):
        self.clicked = False
        self.clicks = 0

    def click(self, timeout=None):
        self.clicked = True
        self.clicks += 1


class _FakeDelayedDescriptionOption(_FakeOption):
    def __init__(self, section):
        super().__init__()
        self.section = section

    def click(self, timeout=None):
        super().click(timeout=timeout)
        self.section.option_selected = True


class _FakeBenefitInput:
    def __init__(self):
        self.value = None
        self.filled = []
        self.pressed = []

    def fill(self, value):
        self.value = value
        self.filled.append(value)

    def input_value(self, timeout=None):
        return self.value or ""

    def press(self, key):
        self.pressed.append(key)
        if key in ("Backspace", "Delete") and self.value in ("", None):
            return None
        if key in ("Control+A", "Meta+A"):
            return None
        if key in ("Escape", "Tab"):
            return None
        return None


class _FakeBenefitDescriptionInputs:
    def __init__(self, section):
        self.section = section

    @property
    def last(self):
        return self.section.description_inputs[-1]

    def count(self):
        return len(self.section.description_inputs)


class _FakeDelayedBenefitDescriptionInputs(_FakeBenefitDescriptionInputs):
    def count(self):
        if self.section.option_selected:
            self.section.description_count_checks += 1
            if (
                self.section.description_count_checks >= 3
                and len(self.section.description_inputs) == 1
            ):
                self.section.description_inputs.append(self.section.new_description_input)
        return len(self.section.description_inputs)


class _FakeBenefitLocator:
    def __init__(self, element, count_value=1):
        self._element = element
        self._count_value = count_value

    @property
    def first(self):
        return self._element

    @property
    def last(self):
        if self._count_value == 0:
            raise AssertionError("No locator matches")
        return self._element

    def filter(self, has_text=None):
        if has_text == "+" and getattr(self._element, "plus_button_has_text", False) is False:
            return _FakeBenefitLocator(self._element, 0)
        return self

    def count(self):
        return self._count_value


class _FakeBenefitClearButton:
    def __init__(self, section):
        self.section = section

    def click(self, timeout=None):
        self.section.clear_clicks += 1
        self.section.search_input.value = ""


class _FakeIneffectiveBenefitClearButton(_FakeBenefitClearButton):
    def click(self, timeout=None):
        self.section.clear_clicks += 1


class _FakeBenefitSection:
    def __init__(self):
        self.search_input = _FakeBenefitInput()
        self.description_input = _FakeBenefitInput()
        self.clicked_add = False
        self.plus_button_has_text = True
        self.description_inputs = [self.description_input]
        self.empty_select_count = 0
        self.clear_clicks = 0
        self.has_clear_button = False

    def locator(self, selector):
        if selector == "div.multiselect":
            return _FakeBenefitLocator(self)
        if "multiselect__clear" in selector or "multiselect__tag-icon" in selector:
            if self.has_clear_button:
                clear_button_class = getattr(
                    self,
                    "clear_button_class",
                    _FakeBenefitClearButton,
                )
                return _FakeBenefitLocator(clear_button_class(self))
            return _FakeBenefitLocator(_FakeBenefitClearButton(self), 0)
        if selector == "input.multiselect__input, input[type='text']":
            return _FakeBenefitLocator(self.search_input)
        if selector == "xpath=.//input[@type='text' and not(ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' multiselect ')])]":
            return _FakeBenefitDescriptionInputs(self)
        if selector == "input[type='text']":
            return _FakeBenefitLocator(self.search_input)
        if selector == "button":
            return _FakeBenefitButtons(self)
        if selector == "input[placeholder='Select benefit'], input[placeholder*='benefit'], .multiselect__placeholder":
            return _FakeBenefitLocator(self.search_input, self.empty_select_count)
        raise AssertionError(selector)

    def click(self, timeout=None):
        self.clicked_add = True


class _FakeBenefitMultiselectRows:
    def __init__(self, first_row, last_row):
        self._first_row = first_row
        self._last_row = last_row

    @property
    def first(self):
        return self._first_row

    @property
    def last(self):
        return self._last_row

    def count(self):
        return 2


class _FakeBenefitMultiselectRow:
    def __init__(self):
        self.search_input = _FakeBenefitInput()
        self.clicks = 0

    def click(self, timeout=None):
        self.clicks += 1

    def locator(self, selector):
        if "multiselect__clear" in selector or "multiselect__tag-icon" in selector:
            return _FakeBenefitLocator(_FakeBenefitClearButton(self), 0)
        if selector == "input.multiselect__input, input[type='text']":
            return _FakeBenefitLocator(self.search_input)
        raise AssertionError(selector)


class _FakeBenefitMultiselectRowsSection(_FakeBenefitSection):
    def __init__(self):
        super().__init__()
        self.first_multiselect = _FakeBenefitMultiselectRow()
        self.last_multiselect = _FakeBenefitMultiselectRow()

    def locator(self, selector):
        if selector == "div.multiselect":
            return _FakeBenefitMultiselectRows(
                self.first_multiselect,
                self.last_multiselect,
            )
        return super().locator(selector)


class _FakePlusButton:
    def __init__(self, section):
        self.section = section

    def click(self, timeout=None):
        self.section.clicked_add = True
        if not hasattr(self.section, "plus_clicks"):
            self.section.description_inputs.append(_FakeBenefitInput())
            return
        self.section.plus_clicks += 1
        if self.section.plus_clicks >= self.section.commit_on_plus_click:
            self.section.description_inputs.append(self.section.new_description_input)


class _FakeBenefitButtons:
    def __init__(self, section):
        self.section = section

    def filter(self, has_text=None):
        return self

    def count(self):
        return 1

    @property
    def last(self):
        return _FakePlusButton(self.section)


class _FakeDeferredBenefitSection(_FakeBenefitSection):
    def __init__(self):
        super().__init__()
        self.existing_description_input = _FakeBenefitInput()
        self.new_description_input = _FakeBenefitInput()
        self.description_inputs = [self.existing_description_input]
        self.plus_clicks = 0
        self.commit_on_plus_click = 1

    def locator(self, selector):
        if selector == "xpath=.//input[@type='text' and not(ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' multiselect ')])]":
            return _FakeBenefitDescriptionInputs(self)
        if selector == "button":
            return _FakeBenefitButtons(self)
        return super().locator(selector)


class _FakeDeferredBenefitPage:
    def __init__(self):
        self.section = _FakeDeferredBenefitSection()

    def locator(self, selector):
        return _FakeBenefitLocator(_FakeBenefitHeading(self.section))


class _FakeRetryBenefitSection(_FakeDeferredBenefitSection):
    def __init__(self):
        super().__init__()
        self.commit_on_plus_click = 2


class _FakeRetryBenefitPage(_FakeDeferredBenefitPage):
    def __init__(self):
        self.section = _FakeRetryBenefitSection()


class _FakeOpaqueBenefitSection(_FakeDeferredBenefitSection):
    def __init__(self):
        super().__init__()
        self.commit_on_plus_click = 99


class _FakeOpaqueBenefitPage(_FakeDeferredBenefitPage):
    def __init__(self):
        self.section = _FakeOpaqueBenefitSection()


class _FakePersistentBenefitSection(_FakeDeferredBenefitSection):
    def __init__(self):
        super().__init__()
        self.description_inputs = [self.existing_description_input]
        self.empty_select_count = 0

    def locator(self, selector):
        if selector == "button":
            return _FakePersistentBenefitButtons(self)
        return super().locator(selector)


class _FakePersistentPlusButton(_FakePlusButton):
    def click(self, timeout=None):
        self.section.clicked_add = True
        self.section.plus_clicks += 1
        self.section.empty_select_count += 1


class _FakePersistentBenefitButtons(_FakeBenefitButtons):
    @property
    def last(self):
        return _FakePersistentPlusButton(self.section)


class _FakePersistentBenefitPage(_FakeDeferredBenefitPage):
    def __init__(self):
        self.section = _FakePersistentBenefitSection()


class _FakeDuplicateBenefitSection(_FakeOpaqueBenefitSection):
    pass


class _FakeDuplicateBenefitPage(_FakeDeferredBenefitPage):
    def __init__(self):
        self.section = _FakeDuplicateBenefitSection()


class _FakeDelayedDescriptionBenefitSection(_FakeDeferredBenefitSection):
    def __init__(self):
        super().__init__()
        self.description_inputs = [self.existing_description_input]
        self.option_selected = False
        self.description_count_checks = 0

    def locator(self, selector):
        if selector == "xpath=.//input[@type='text' and not(ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' multiselect ')])]":
            return _FakeDelayedBenefitDescriptionInputs(self)
        return super().locator(selector)


class _FakeDelayedDescriptionBenefitPage(_FakeDeferredBenefitPage):
    def __init__(self):
        self.section = _FakeDelayedDescriptionBenefitSection()


class _FakeBenefitHeading:
    def __init__(self, section):
        self.section = section

    def locator(self, selector):
        return self.section


class _FakeStructuredBenefitPage:
    def __init__(self):
        self.section = _FakeBenefitSection()

    def locator(self, selector):
        return _FakeBenefitLocator(_FakeBenefitHeading(self.section))


class _FakeIconOnlyBenefitPage(_FakeStructuredBenefitPage):
    def __init__(self):
        super().__init__()
        self.section.plus_button_has_text = False


class _FakeIneffectiveClearBenefitPage(_FakeStructuredBenefitPage):
    def __init__(self):
        super().__init__()
        self.section.has_clear_button = True
        self.section.clear_button_class = _FakeIneffectiveBenefitClearButton


class _FakeBenefitMultiselectRowsPage(_FakeStructuredBenefitPage):
    def __init__(self):
        self.section = _FakeBenefitMultiselectRowsSection()


class JobDetailHelpersTest(unittest.TestCase):
    def test_get_job_detail_accepts_column_without_trailing_space(self):
        job = {"Job Detail": "Fill this detail"}

        self.assertEqual(_get_job_detail(job), "Fill this detail")

    def test_job_detail_selector_accepts_current_ui_label(self):
        xpath = _job_detail_label_xpath()

        self.assertIn("Job Detail", xpath)

    def test_job_detail_textarea_score_prefers_job_detail_fields(self):
        detail_meta = {
            "name": "job_description",
            "id": "",
            "placeholder": "Job Detail",
            "aria": "",
        }
        note_meta = {
            "name": "note",
            "id": "internal_note",
            "placeholder": "Note",
            "aria": "",
        }

        self.assertGreater(
            _job_detail_textarea_score(detail_meta),
            _job_detail_textarea_score(note_meta),
        )

    def test_job_detail_html_converts_lines_to_paragraphs_and_escapes_text(self):
        html = _job_detail_html("Line <one>\n\nLine & two")

        self.assertEqual(html, "<p>Line &lt;one&gt;</p><p>Line &amp; two</p>")

    def test_job_list_items_ignores_blank_lines(self):
        self.assertEqual(_job_list_items(" A \n\n B \r\n "), ["A", "B"])

    def test_get_job_benefits_uses_benefit_column_lines(self):
        job = {"Benefit": "Annual Bonuses\nHealth care"}

        self.assertEqual(
            _get_job_benefits(job, "9000000", "25000000"),
            [
                ("Annual Bonuses", dict(BENEFITS_DATA)["Annual Bonuses"]),
                ("Health care", dict(BENEFITS_DATA)["Health care"]),
            ],
        )

    def test_get_job_benefits_supports_inline_description(self):
        job = {"Benefit": "Health care: Custom health care text"}

        self.assertEqual(
            _get_job_benefits(job, "", ""),
            [("Health care", "Custom health care text")],
        )

    def test_get_job_benefits_maps_description_lines_to_topdev_keywords(self):
        job = {
            "Benefit": (
                "Thưởng dịp lễ tết, thưởng thành tích gắn với hiệu suất công việc/kết quả kinh doanh\n"
                "Junior: Từ 9.000.000 - 25.000.000, theo năng suất lao động"
            )
        }

        self.assertEqual(
            _get_job_benefits(job, "", ""),
            [
                ("Annual Bonuses", "Thưởng dịp lễ tết, thưởng thành tích gắn với hiệu suất công việc/kết quả kinh doanh"),
                ("Competitive Salary", "Junior: Từ 9.000.000 - 25.000.000, theo năng suất lao động"),
            ],
        )

    def test_get_job_benefits_maps_current_jd_description_lines_in_order(self):
        job = {
            "Benefit ": (
                "Thưởng dịp lễ tết, Thưởng thành tích gắn với hiệu suất công việc/kết quả kinh doanh\n"
                "Đãi ngộ gắn kết (Tặng quà sinh nhật, quà Tết Nguyên đán, đãi ngộ thâm niên.....)\n"
                "Bảo hiểm chăm sóc sức khỏe cho CBNV/người thân với các đặc quyền độc đáo\n"
                "Du lịch/nghỉ dưỡng hằng năm trong nước & nước ngoài\n"
                "Được tư vấn, hỗ trợ tài chính & trải nghiệm các sản phẩm tài chính cá nhân, bảo hiểm... theo các tệp sản phẩm của tập đoàn\n"
                "Lộ trình thăng tiến rõ ràng, cơ hội phát triển với các nhóm nghề nghiệp tại Ngân hàng.\n"
                "Được dẫn dắt bởi Lãnh đạo danh tiếng, được đồng hành và \"\"Learning on Jobs\"\" cùng các Quản lý và đồng nghiệp ưu tú.\n"
                "Môi trường làm việc trẻ trung, chuyên nghiệp, ứng dụng toàn diện các phương pháp làm việc mới và các nền tảng công nghệ tiên tiến nhất trên thế giới.\n"
                "Junior: Từ 9.000.000 – đến 25.000.000, theo năng suất lao động.\n"
                "Mid-Level: Từ 12.000.000 – đến 30.000.000, theo năng suất lao động\n"
                "Professional: Từ 15.000.000 – đến 35.000.000, theo năng suất lao động"
            )
        }

        benefits = _get_job_benefits(job, "", "")

        self.assertEqual(
            [name for name, _ in benefits],
            [
                "Annual Bonuses",
                "Social events",
                "Health care",
                "Travel opportunities and global exposure",
                "Employee discounts",
                "Career Growth Opportunities",
                "Professional Development",
                "Working environment",
                "Competitive Salary",
                "Competitive Salary",
                "Competitive Salary",
            ],
        )
        self.assertEqual(
            benefits[3],
            (
                "Travel opportunities and global exposure",
                "Du lịch/nghỉ dưỡng hằng năm trong nước & nước ngoài",
            ),
        )

    def test_get_job_benefits_injects_salary_range_for_competitive_salary(self):
        job = {"Benefit": "Competitive Salary"}

        self.assertEqual(
            _get_job_benefits(job, "9000000", "25000000"),
            [("Competitive Salary", "Junior: Từ 9.000.000 đến 25.000.000, theo năng suất lao động")],
        )

    def test_get_job_benefits_keeps_all_competitive_salary_level_lines(self):
        job = {
            "Benefit": (
                "Junior: Từ 9.000.000  đến 25.000.000, theo năng suất lao động.\n"
                "Mid-Level: Từ 12.000.000  đến 30.000.000, theo năng suất lao động\n"
                "Professional: Từ 15.000.000  đến 35.000.000, theo năng suất lao động."
            )
        }

        self.assertEqual(
            _get_job_benefits(job, "", ""),
            [
                ("Competitive Salary", "Junior: Từ 9.000.000  đến 25.000.000, theo năng suất lao động."),
                ("Competitive Salary", "Mid-Level: Từ 12.000.000  đến 30.000.000, theo năng suất lao động"),
                ("Competitive Salary", "Professional: Từ 15.000.000  đến 35.000.000, theo năng suất lao động."),
            ],
        )

    def test_recruitment_rounds_are_fixed_in_order(self):
        self.assertEqual(_recruitment_rounds(), ["CV screenning", "HR Interview"])

    def test_salary_input_value_normalizes_excel_numbers(self):
        self.assertEqual(_salary_input_value("9,000,000"), "9000000")
        self.assertEqual(_salary_input_value("9.000.000"), "9000000")
        self.assertEqual(_salary_input_value(25000000.0), "25000000")

    def test_salary_display_range_formats_vnd_range(self):
        self.assertEqual(
            _salary_display_range("9000000", "25000000"),
            "9.000.000 - 25.000.000 VND",
        )

    def test_fill_salary_range_uses_inputs_inside_salary_section(self):
        page = _FakeSalaryPage()

        _fill_salary_range(page, "9000000", "25000000")

        self.assertEqual(
            page.section.last_selector,
            "input:not([type='checkbox']):not([type='radio']):not([type='hidden'])",
        )
        self.assertEqual(page.section.inputs[0].value, "9000000")
        self.assertEqual(page.section.inputs[1].value, "25000000")

    def test_wait_for_multiselect_option_polls_visible_option_with_short_timeout(self):
        page = _FakePage()
        option = object()
        multiselect = _FakeMultiselect(option)

        found = _wait_for_multiselect_option(
            page,
            multiselect,
            "Business, Finance",
            "Business",
            timeout=1200,
        )

        self.assertIs(found, option)
        self.assertEqual(page.wait_args[2], 1200)
        self.assertEqual(multiselect.evaluate_args[1], ["Business, Finance", "Business"])

    def test_step3_does_not_pause_before_role_with_fixed_sleep(self):
        source = inspect.getsource(step3_basic_info)

        self.assertNotIn("time.sleep(1.5)", source)

    def test_step3_uses_fast_working_location_select_and_no_fixed_yoe_sleep(self):
        source = inspect.getsource(step3_basic_info)

        self.assertIn('filter_wait=0.1', source)
        self.assertNotIn("time.sleep(0.5)", source)

    def test_vue_select_uses_configured_filter_and_close_waits(self):
        source = inspect.getsource(_vue_select)

        self.assertNotIn("time.sleep(0.5)", source)
        self.assertNotIn("time.sleep(0.3)", source)
        self.assertIn("time.sleep(filter_wait)", source)
        self.assertIn("time.sleep(close_wait)", source)

    def test_add_benefit_uses_short_configured_waits_between_items(self):
        source = inspect.getsource(_add_benefit)

        self.assertNotIn("time.sleep(0.4)", source)
        self.assertNotIn("time.sleep(0.6)", source)
        self.assertNotIn("deadline = time.time() + 3", source)
        self.assertIn("commit_timeout", source)

    def test_add_benefit_uses_document_aware_multiselect_option_lookup(self):
        page = _FakeBenefitPage()
        option = _FakeOption()

        with patch("topdev_automation._wait_for_multiselect_option", return_value=option) as wait:
            _add_benefit(page, "Annual Bonuses", "Bonus description")

        self.assertTrue(option.clicked)
        self.assertEqual(wait.call_args.args[2], "Annual Bonuses")
        self.assertIn("Annual Bonuses", page.root.filled)
        self.assertIn("Bonus description", page.root.filled)

    def test_add_benefit_does_not_fill_visible_multiselect_search_as_description(self):
        page = _FakeStructuredBenefitPage()
        option = _FakeOption()

        with patch("topdev_automation._wait_for_multiselect_option", return_value=option):
            _add_benefit(page, "Annual Bonuses", "Bonus description")

        self.assertEqual(page.section.search_input.value, "")
        self.assertIn("Annual Bonuses", page.section.search_input.filled)
        self.assertIn("Bonus description", page.section.description_input.filled)

    def test_add_benefit_falls_back_to_last_button_when_plus_icon_has_no_text(self):
        page = _FakeIconOnlyBenefitPage()
        option = _FakeOption()

        with patch("topdev_automation._wait_for_multiselect_option", return_value=option):
            _add_benefit(page, "Annual Bonuses", "Bonus description")

        self.assertTrue(page.section.clicked_add)

    def test_add_benefit_commits_description_with_plus_before_next_item(self):
        page = _FakeDeferredBenefitPage()
        option = _FakeOption()

        with patch("topdev_automation._wait_for_multiselect_option", return_value=option):
            _add_benefit(page, "Competitive Salary", "Junior salary description")

        self.assertTrue(page.section.clicked_add)
        self.assertIn("Junior salary description", page.section.existing_description_input.filled)
        self.assertEqual(page.section.plus_clicks, 1)

    def test_add_benefit_retries_plus_when_description_was_not_committed(self):
        page = _FakeRetryBenefitPage()
        option = _FakeOption()

        with patch("topdev_automation._wait_for_multiselect_option", return_value=option):
            _add_benefit(page, "Competitive Salary", "Junior salary description")

        self.assertEqual(page.section.plus_clicks, 2)
        self.assertEqual(len(page.section.description_inputs), 2)

    def test_add_benefit_does_not_stop_when_ui_commit_signal_is_opaque(self):
        page = _FakeOpaqueBenefitPage()
        option = _FakeOption()

        with patch("topdev_automation._wait_for_multiselect_option", return_value=option):
            _add_benefit(page, "Annual Bonuses", "Bonus description")

        self.assertEqual(page.section.plus_clicks, 2)

    def test_add_benefit_accepts_new_empty_select_as_commit_signal(self):
        page = _FakePersistentBenefitPage()
        option = _FakeOption()

        with patch("topdev_automation._wait_for_multiselect_option", return_value=option):
            _add_benefit(page, "Annual Bonuses", "Bonus description")

        self.assertEqual(page.section.plus_clicks, 1)
        self.assertEqual(page.section.existing_description_input.value, "Bonus description")

    def test_add_benefit_clears_stale_select_text_for_duplicate_benefit(self):
        page = _FakeStructuredBenefitPage()
        page.section.search_input.value = "Competitive Salary"
        page.section.has_clear_button = True
        option = _FakeOption()

        with patch("topdev_automation._wait_for_multiselect_option", return_value=option):
            _add_benefit(page, "Competitive Salary", "Mid-Level salary description")

        self.assertGreaterEqual(page.section.clear_clicks, 1)
        self.assertNotEqual(page.section.search_input.filled[0], "")
        self.assertIn("Competitive Salary", page.section.search_input.filled)

    def test_add_benefit_falls_back_when_clear_icon_leaves_select_text(self):
        page = _FakeIneffectiveClearBenefitPage()
        option = _FakeOption()

        with patch("topdev_automation._wait_for_multiselect_option", return_value=option):
            _add_benefit(page, "Competitive Salary", "Junior salary description")

        self.assertGreaterEqual(page.section.clear_clicks, 1)
        self.assertEqual(page.section.search_input.value, "")

    def test_add_benefit_targets_last_multiselect_row(self):
        page = _FakeBenefitMultiselectRowsPage()
        option = _FakeOption()

        with patch("topdev_automation._wait_for_multiselect_option", return_value=option):
            _add_benefit(page, "Competitive Salary", "Junior salary description")

        self.assertNotIn(
            "Competitive Salary",
            page.section.first_multiselect.search_input.filled,
        )
        self.assertIn(
            "Competitive Salary",
            page.section.last_multiselect.search_input.filled,
        )

    def test_add_benefit_waits_for_new_description_input_after_select(self):
        page = _FakeDelayedDescriptionBenefitPage()
        option = _FakeDelayedDescriptionOption(page.section)

        with patch("topdev_automation._wait_for_multiselect_option", return_value=option):
            _add_benefit(page, "Competitive Salary", "Junior salary description")

        self.assertNotIn(
            "Junior salary description",
            page.section.existing_description_input.filled,
        )
        self.assertIn(
            "Junior salary description",
            page.section.new_description_input.filled,
        )

    def test_add_benefit_waits_for_new_description_input_after_duplicate_select(self):
        page = _FakeDelayedDescriptionBenefitPage()
        option = _FakeDelayedDescriptionOption(page.section)

        with patch("topdev_automation._wait_for_multiselect_option", return_value=option):
            _add_benefit(
                page,
                "Competitive Salary",
                "Mid-Level salary description",
                select_twice=True,
            )

        self.assertNotIn(
            "Mid-Level salary description",
            page.section.existing_description_input.filled,
        )
        self.assertIn(
            "Mid-Level salary description",
            page.section.new_description_input.filled,
        )

    def test_add_benefit_selects_duplicate_option_twice_before_description(self):
        page = _FakeDelayedDescriptionBenefitPage()
        option = _FakeDelayedDescriptionOption(page.section)

        with patch("topdev_automation._wait_for_multiselect_option", return_value=option) as wait:
            _add_benefit(
                page,
                "Competitive Salary",
                "Mid-Level salary description",
                select_twice=True,
            )

        self.assertEqual(wait.call_count, 2)
        self.assertEqual(option.clicks, 2)
        self.assertIn(
            "Mid-Level salary description",
            page.section.new_description_input.filled,
        )

    def test_add_benefit_requires_commit_for_duplicate_benefit_names(self):
        page = _FakeDuplicateBenefitPage()
        option = _FakeOption()

        with patch("topdev_automation._wait_for_multiselect_option", return_value=option):
            with self.assertRaisesRegex(Exception, "chưa được thêm"):
                _add_benefit(
                    page,
                    "Competitive Salary",
                    "Junior salary description",
                    require_commit=True,
                )

    def test_step9_requires_commit_for_duplicate_benefit_names(self):
        source = inspect.getsource(step9_salary_benefits)

        self.assertIn("is_repeated_previous_benefit = benefit_name == previous_benefit_name", source)
        self.assertIn("require_commit=is_repeated_previous_benefit", source)
        self.assertIn("select_twice=is_repeated_previous_benefit", source)


if __name__ == "__main__":
    unittest.main()
