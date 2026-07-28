"""
CORE AGENT APP (Danh cho Role 4: Core Agent Developer)
File chinh ghep noi tat ca cac thanh phan: Tools + Prompts + Test Cases + Multi-Provider.
"""

import json
import os
import sys
from dotenv import load_dotenv

# Đảm bảo import các module cùng thư mục src/ hoạt động mượt mà
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Đảm bảo in ra Tiếng Việt và Emojis không bị lỗi trên Windows Console
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

# Import cac thanh phan tu file cua Role 2, Role 3 & Multi-Provider Adapter
from tools import AVAILABLE_TOOLS, screen_resume, check_interviewer_availability, schedule_interview, TOOL_SPECS
from prompts import CHATBOT_BASELINE_PROMPT, REACT_SYSTEM_PROMPT, MAX_ITERATIONS, SAFE_FALLBACK_MESSAGE
from providers import get_llm_provider

load_dotenv()

def load_test_cases():
    """Đọc bộ test cases từ config/test_cases.json của Role 1"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, "config", "test_cases.json")
    
    # Fallback kiểm tra nếu file ở thư mục hiện tại
    if not os.path.exists(config_path):
        config_path = "test_cases.json"
        
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_baseline_chatbot(user_query: str, provider):
    """
    Dựng Chatbot gốc (Baseline) không có công cụ.
    
    Returns:
        dict: {'question': str, 'response': str, 'category': str}
    """
    print(f"\n{'='*60}")
    print(f"[CHATBOT BASELINE] Test Case")
    print(f"{'='*60}")
    print(f"Cau hoi: {user_query}")
    print(f"{'-'*60}")
    
    # Goi LLM Provider thuc hien sinh cau tra loi
    response = provider.generate(user_query, system_prompt=CHATBOT_BASELINE_PROMPT)
    print(f"Chatbot tra loi:\n{response}")
    print(f"{'='*60}")
    
    # Trả về dict để Role 5 ghi vào trace_eval.md
    return {
        "question": user_query,
        "response": response,
    }


def run_react_agent(user_query: str, provider):
    """
    Dựng vòng lặp ReAct Agent (Thought -> Action -> Observation) có Guardrails.
    
    NOTE: Đây là phiên bản demo cho Mốc 2. Phiên bản đầy đủ sẽ được implement ở Mốc 4.
    """
    print(f"\n[REACT AGENT] Cau hoi: {user_query}")
    
    # Tạo conversation context cho ReAct
    conversation_history = []
    
    # Build prompt với system prompt ReAct
    prompt = REACT_SYSTEM_PROMPT + f"\n\nCâu hỏi: {user_query}"
    
    # Thêm conversation history nếu có
    if conversation_history:
        prompt += "\n\nLịch sử hội thoại:\n" + "\n".join(conversation_history)
    
    prompt += "\n\nHãy suy nghĩ và hành động:"
    
    # Goi LLM de phan tich
    print("\n--- Buoc 1: Goi LLM phan tich cau hoi ---")
    response = provider.generate(prompt, system_prompt="")
    
    # Demo: Hien thi response va chay thu mot tool
    print(f"\nLLM Response:\n{response}")
    
    # Demo voi tool screen_resume cho test case #3
    if "Nguyen Van A" in user_query and "Data Engineer" in user_query:
        print("\n--- Demo: Goi tool screen_resume ---")
        obs = screen_resume("Nguyen Van A", "Data Engineer")
        print(f"Observation: {obs}")
        conversation_history.append(f"Observation: {obs}")
    
    print(f"\n{'='*60}")
    print("Ghi chu: ReAct Agent day du se duoc implement o Moc 4")
    print(f"{'='*60}")


if __name__ == "__main__":
    print("==================================================")
    print("DAI HOC VINUNI - BAI LAB 3: CHATBOT VS REACT AGENT")
    print("==================================================")
    
    # Khoi tao Multi-Provider LLM Adapter (Doc tu bien moi truong LLM_PROVIDER)
    provider = get_llm_provider()
    model_name = getattr(provider, "model_name", "Offline Mock Mode")
    print(f"LLM Provider dang hoat dong: {provider.__class__.__name__} (Model: {model_name})")
    
    # Load test cases
    tests = load_test_cases()
    print(f"Da tai thanh cong {len(tests)} Test Cases tu config/test_cases.json\n")
    
    # ====================================================================
    # MOC 2: DEMO CHATBOT BASELINE
    # ====================================================================
    print("\n" + "="*60)
    print("MOC 2: CHAY CHATBOT BASELINE TREN TAT CA TEST CASES")
    print("="*60 + "\n")
    
    baseline_results = []
    
    for test in tests:
        print(f"\nTest Case #{test['id']} - [{test['category']}]")
        print(f"   Cau hoi: {test['question'][:80]}...")
        
        # Chay baseline chatbot
        result = run_baseline_chatbot(test["question"], provider)
        baseline_results.append({
            "id": test["id"],
            "category": test["category"],
            "question": test["question"],
            "response": result["response"],
        })
    
    # Tom tat ket qua
    print("\n" + "="*60)
    print("TOM TAT KET QUA CHATBOT BASELINE")
    print("="*60)
    for r in baseline_results:
        print(f"  Test #{r['id']}: {r['category']}")
    print(f"\nHoan thanh Moc 2! Role 5 can ghi ket qua vao docs/trace_eval.md")
    
    # ====================================================================
    # DEMO: REACT AGENT (se hoan thien o Moc 4)
    # ====================================================================
    print("\n" + "="*60)
    print("DEMO: REACT AGENT (Chay thu Test Case #3)")
    print("="*60 + "\n")
    
    # Chay ReAct Agent demo
    sample_query = tests[2]["question"]
    run_react_agent(sample_query, provider)
