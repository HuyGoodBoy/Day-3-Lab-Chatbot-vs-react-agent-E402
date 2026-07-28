"""
🛠️ TOOL REGISTRY & SCHEMAS (Dành cho Role 2: Tool & Spec Engineer)
Nơi khai báo tất cả các "món đồ nghề" mà ReAct Agent có thể gọi.

Chủ đề: Trợ Lý Sàng Lọc Hồ Sơ Tuyển Dụng & Hẹn Phỏng Vấn

🛡️ NGUYÊN TẮC AN TOÀN (Mốc 3): Mọi tool LUÔN trả về chuỗi (str), kể cả khi gặp lỗi.
Không tool nào được phép ném Exception làm sập vòng lặp ReAct của Agent.
"""

import datetime
import functools

# ============================================================
# 📦 MOCK DATA (Giả lập cơ sở dữ liệu tuyển dụng)
# ============================================================

# Hồ sơ ứng viên: kỹ năng & số năm kinh nghiệm
CANDIDATES_DB = {
    "nguyễn văn a": {"skills": ["python", "sql", "machine learning"], "experience_years": 3},
    "trần thị b": {"skills": ["java", "spring boot", "docker"], "experience_years": 5},
    "lê văn c": {"skills": ["react", "javascript", "css"], "experience_years": 1},
}

# Yêu cầu kỹ năng theo vị trí tuyển dụng
POSITIONS_DB = {
    "data engineer": {"required_skills": ["python", "sql"], "min_experience": 2},
    "backend developer": {"required_skills": ["java", "spring boot"], "min_experience": 3},
    "frontend developer": {"required_skills": ["react", "javascript"], "min_experience": 2},
}

# Lịch bận của người phỏng vấn: {tên: {ngày: [khung giờ đã bận]}}
INTERVIEWER_CALENDAR = {
    "chị hương (hr)": {"2026-08-01": ["09:00", "14:00"], "2026-08-02": ["10:00"]},
    "anh minh (tech lead)": {"2026-08-01": ["10:00", "11:00", "15:00"]},
}

# Lịch phỏng vấn đã đặt thành công (được cập nhật khi gọi schedule_interview)
BOOKED_INTERVIEWS = []

# Khung giờ phỏng vấn hợp lệ trong ngày làm việc (mỗi slot 1 tiếng)
WORK_HOURS = [f"{h:02d}:00" for h in range(9, 17)]


# ============================================================
# 🛡️ GUARDRAILS TẦNG TOOL (Mốc 3) - Kiểm tra đầu vào & chống crash
# ============================================================

def safe_tool(func):
    """
    Decorator bọc quanh mỗi tool: mọi Exception ngoài dự kiến đều được chuyển thành
    chuỗi 'LỖI: ...' để Agent đọc như một Observation bình thường thay vì làm sập App.

    Đây là lớp phòng thủ cuối cùng, phòng khi có lỗi lập trình chưa lường trước.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            return (
                f"LỖI: Công cụ '{func.__name__}' gặp sự cố ngoài dự kiến "
                f"({type(e).__name__}: {e}). Vui lòng kiểm tra lại tham số đầu vào."
            )
    return wrapper


def _clean_text(value, field_name: str):
    """
    Chuẩn hóa tham số dạng chuỗi (chống None, số, chuỗi rỗng do Agent sinh sai).

    Returns:
        tuple: (giá_trị_đã_chuẩn_hóa, None) nếu hợp lệ, hoặc (None, chuỗi_LỖI) nếu không hợp lệ.
    """
    if not isinstance(value, str) or not value.strip():
        return None, f"LỖI: Tham số '{field_name}' phải là chuỗi không rỗng (nhận được: {value!r})."
    return value.strip(), None


def _validate_date(value):
    """
    Kiểm tra ngày phải đúng định dạng YYYY-MM-DD và là ngày có thật trên lịch.

    Returns:
        tuple: (ngày_hợp_lệ, None) hoặc (None, chuỗi_LỖI). Chặn các ngày bịa như '32/13/2026'.
    """
    cleaned, err = _clean_text(value, "date")
    if err:
        return None, err
    try:
        datetime.datetime.strptime(cleaned, "%Y-%m-%d")
    except ValueError:
        return None, (
            f"LỖI: Ngày '{value}' không hợp lệ hoặc không tồn tại trên lịch. "
            f"Vui lòng dùng định dạng YYYY-MM-DD (ví dụ: 2026-08-01)."
        )
    return cleaned, None


def _validate_time(value):
    """
    Kiểm tra giờ phải đúng định dạng HH:MM và nằm trong khung giờ phỏng vấn cho phép.

    Returns:
        tuple: (giờ_hợp_lệ, None) hoặc (None, chuỗi_LỖI). Chặn các giờ vô lý như '25:00'.
    """
    cleaned, err = _clean_text(value, "time")
    if err:
        return None, err
    try:
        datetime.datetime.strptime(cleaned, "%H:%M")
    except ValueError:
        return None, (
            f"LỖI: Giờ '{value}' không hợp lệ. Vui lòng dùng định dạng HH:MM (ví dụ: 09:00)."
        )
    if cleaned not in WORK_HOURS:
        return None, (
            f"LỖI: Giờ '{cleaned}' nằm ngoài khung giờ phỏng vấn cho phép. "
            f"Chỉ nhận các slot: {', '.join(WORK_HOURS)}."
        )
    return cleaned, None


# ============================================================
# 🛠️ TOOLS
# ============================================================

@safe_tool
def screen_resume(candidate_name: str, position: str) -> str:
    """
    Sàng lọc & chấm điểm mức độ phù hợp giữa hồ sơ ứng viên và vị trí tuyển dụng.

    Args:
        candidate_name (str): Tên ứng viên (Ví dụ: 'Nguyễn Văn A')
        position (str): Tên vị trí tuyển dụng (Ví dụ: 'Data Engineer')

    Returns:
        str: Kết quả sàng lọc gồm điểm phù hợp (%), kỹ năng khớp/thiếu và kết luận Đạt/Không đạt.
             Trả về chuỗi LỖI nếu tham số rỗng/sai kiểu, hoặc không tìm thấy ứng viên/vị trí
             trong hệ thống (KHÔNG bịa hồ sơ cho ứng viên chưa tồn tại).
    """
    name, err = _clean_text(candidate_name, "candidate_name")
    if err:
        return err

    pos, err = _clean_text(position, "position")
    if err:
        return err

    candidate = CANDIDATES_DB.get(name.lower())
    if candidate is None:
        return f"LỖI: Không tìm thấy hồ sơ ứng viên '{candidate_name}' trong hệ thống."

    role = POSITIONS_DB.get(pos.lower())
    if role is None:
        return f"LỖI: Không tìm thấy vị trí tuyển dụng '{position}' trong danh sách đang mở."

    required_skills = role["required_skills"]
    if not required_skills:
        return f"LỖI: Vị trí '{position}' chưa khai báo kỹ năng yêu cầu nên không thể chấm điểm."

    matched_skills = set(candidate["skills"]) & set(required_skills)
    missing_skills = set(required_skills) - set(candidate["skills"])
    skill_score = len(matched_skills) / len(required_skills) * 100
    exp_ok = candidate["experience_years"] >= role["min_experience"]

    verdict = "ĐẠT ✅" if skill_score >= 50 and exp_ok else "KHÔNG ĐẠT ❌"

    return (
        f"Sàng lọc '{candidate_name}' cho vị trí '{position}':\n"
        f"- Độ khớp kỹ năng: {skill_score:.0f}% (Khớp: {sorted(matched_skills) or 'Không có'}, "
        f"Thiếu: {sorted(missing_skills) or 'Không'})\n"
        f"- Kinh nghiệm: {candidate['experience_years']} năm "
        f"(Yêu cầu tối thiểu: {role['min_experience']} năm)\n"
        f"- Kết luận: {verdict}"
    )


@safe_tool
def check_interviewer_availability(interviewer: str, date: str) -> str:
    """
    Tra cứu các khung giờ còn trống của người phỏng vấn trong một ngày cụ thể.

    Args:
        interviewer (str): Tên người phỏng vấn (Ví dụ: 'Chị Hương (HR)')
        date (str): Ngày cần kiểm tra, định dạng YYYY-MM-DD (Ví dụ: '2026-08-01')

    Returns:
        str: Danh sách khung giờ trống trong ngày làm việc (09:00 - 16:00, mỗi slot 1 tiếng).
             Trả về chuỗi LỖI nếu tham số rỗng/sai kiểu, không tìm thấy người phỏng vấn,
             hoặc ngày không hợp lệ / không tồn tại trên lịch.
    """
    name, err = _clean_text(interviewer, "interviewer")
    if err:
        return err

    valid_date, err = _validate_date(date)
    if err:
        return err

    key = name.lower()
    if key not in INTERVIEWER_CALENDAR:
        return f"LỖI: Không tìm thấy người phỏng vấn '{interviewer}' trong hệ thống."

    date = valid_date
    busy_slots = INTERVIEWER_CALENDAR[key].get(date, [])
    free_slots = [slot for slot in WORK_HOURS if slot not in busy_slots]

    if not free_slots:
        return f"{interviewer} đã kín lịch vào ngày {date}. Không còn khung giờ trống."

    return f"Khung giờ trống của {interviewer} ngày {date}: {', '.join(free_slots)}."


@safe_tool
def schedule_interview(candidate_name: str, interviewer: str, date: str, time: str) -> str:
    """
    Đặt lịch phỏng vấn cho ứng viên với người phỏng vấn, nếu khung giờ còn trống.

    Args:
        candidate_name (str): Tên ứng viên (phải đã tồn tại trong hệ thống)
        interviewer (str): Tên người phỏng vấn
        date (str): Ngày phỏng vấn, định dạng YYYY-MM-DD
        time (str): Giờ phỏng vấn, định dạng HH:MM, phải thuộc khung giờ làm việc (09:00 - 16:00)

    Returns:
        str: Thông báo đặt lịch thành công, hoặc chuỗi LỖI nếu tham số sai kiểu/rỗng,
             ứng viên hoặc người phỏng vấn không tồn tại, ngày/giờ không hợp lệ,
             hoặc khung giờ đã có người khác đặt. Lịch CHỈ bị thay đổi khi mọi kiểm tra đều qua.
    """
    name, err = _clean_text(candidate_name, "candidate_name")
    if err:
        return err

    interviewer_name, err = _clean_text(interviewer, "interviewer")
    if err:
        return err

    valid_date, err = _validate_date(date)
    if err:
        return err

    valid_time, err = _validate_time(time)
    if err:
        return err

    # Không đặt lịch cho hồ sơ không có thật (chống bịa ứng viên)
    if name.lower() not in CANDIDATES_DB:
        return (
            f"LỖI: Không tìm thấy hồ sơ ứng viên '{candidate_name}' trong hệ thống. "
            f"Cần có hồ sơ hợp lệ trước khi đặt lịch phỏng vấn."
        )

    key = interviewer_name.lower()
    if key not in INTERVIEWER_CALENDAR:
        return f"LỖI: Không tìm thấy người phỏng vấn '{interviewer}' trong hệ thống."

    busy_slots = INTERVIEWER_CALENDAR[key].setdefault(valid_date, [])
    if valid_time in busy_slots:
        return (
            f"LỖI: {interviewer_name} đã bận vào lúc {valid_time} ngày {valid_date}. "
            f"Vui lòng chọn khung giờ khác."
        )

    busy_slots.append(valid_time)
    BOOKED_INTERVIEWS.append({
        "candidate": name,
        "interviewer": interviewer_name,
        "date": valid_date,
        "time": valid_time,
    })

    return (
        f"✅ Đặt lịch thành công: Ứng viên '{name}' phỏng vấn với '{interviewer_name}' "
        f"lúc {valid_time} ngày {valid_date}."
    )


# Danh sách các tool được đăng ký để Agent sử dụng
AVAILABLE_TOOLS = {
    "screen_resume": screen_resume,
    "check_interviewer_availability": check_interviewer_availability,
    "schedule_interview": schedule_interview,
}


# ============================================================
# 📑 TOOL SPECS (Mô tả chuẩn hóa - dùng để nhúng vào REACT_SYSTEM_PROMPT)
# ============================================================

TOOL_SPECS = [
    {
        "name": "screen_resume",
        "description": (
            "Sàng lọc & chấm điểm mức độ phù hợp giữa hồ sơ ứng viên và vị trí tuyển dụng. "
            "Dùng khi cần biết một ứng viên cụ thể có ĐẠT yêu cầu của một vị trí cụ thể hay không."
        ),
        "parameters": {
            "candidate_name": "str - Tên ứng viên (Ví dụ: 'Nguyễn Văn A')",
            "position": "str - Tên vị trí tuyển dụng (Ví dụ: 'Data Engineer')",
        },
        "failure_modes": [
            "Tham số rỗng hoặc sai kiểu -> trả về chuỗi LỖI.",
            "Ứng viên chưa có hồ sơ trong hệ thống -> trả về chuỗi LỖI, KHÔNG được bịa kết quả.",
            "Vị trí tuyển dụng không tồn tại -> trả về chuỗi LỖI.",
        ],
    },
    {
        "name": "check_interviewer_availability",
        "description": (
            "Tra cứu các khung giờ còn trống của một người phỏng vấn trong một ngày cụ thể. "
            "Dùng trước khi đặt lịch để biết còn giờ trống hay không."
        ),
        "parameters": {
            "interviewer": "str - Tên người phỏng vấn (Ví dụ: 'Chị Hương (HR)')",
            "date": "str - Ngày cần kiểm tra, định dạng YYYY-MM-DD",
        },
        "failure_modes": [
            "Tham số rỗng hoặc sai kiểu -> trả về chuỗi LỖI.",
            "Người phỏng vấn không có trong hệ thống -> trả về chuỗi LỖI.",
            "Ngày sai định dạng hoặc không tồn tại (VD: 32/13/2026) -> trả về chuỗi LỖI.",
            "Ngày đã kín lịch -> báo không còn khung giờ trống (không phải lỗi).",
        ],
    },
    {
        "name": "schedule_interview",
        "description": (
            "Đặt lịch phỏng vấn cho ứng viên với người phỏng vấn vào một ngày/giờ cụ thể. "
            "Chỉ nên gọi sau khi đã xác nhận ứng viên ĐẠT (qua screen_resume) và khung giờ còn trống "
            "(qua check_interviewer_availability)."
        ),
        "parameters": {
            "candidate_name": "str - Tên ứng viên",
            "interviewer": "str - Tên người phỏng vấn",
            "date": "str - Ngày phỏng vấn, định dạng YYYY-MM-DD",
            "time": "str - Giờ phỏng vấn, định dạng HH:MM, thuộc khung 09:00 - 16:00",
        },
        "failure_modes": [
            "Tham số rỗng hoặc sai kiểu -> trả về chuỗi LỖI.",
            "Ứng viên chưa có hồ sơ trong hệ thống -> từ chối đặt lịch, trả về chuỗi LỖI.",
            "Người phỏng vấn không có trong hệ thống -> trả về chuỗi LỖI.",
            "Ngày/giờ vô lý (VD: 32/13/2026, 25:00) -> trả về chuỗi LỖI, KHÔNG ghi vào lịch.",
            "Khung giờ đã có người đặt -> trả về chuỗi LỖI, gợi ý chọn giờ khác.",
        ],
    },
]
