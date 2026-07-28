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
    
    Returns:
        dict: {'question': str, 'response': str, 'trace': list}
    """
    print(f"\n{'='*60}")
    print(f"[REACT AGENT] Processing Query")
    print(f"{'='*60}")
    print(f"Cau hoi: {user_query}")
    print(f"{'-'*60}")
    
    conversation_history = []
    iteration = 0
    trace = []
    
    while iteration < MAX_ITERATIONS:
        iteration += 1
        print(f"\n--- Vong lap #{iteration} ---")
        
        # Build prompt
        prompt = REACT_SYSTEM_PROMPT + "\n\n"
        prompt += f"Câu hỏi: {user_query}\n\n"
        
        if conversation_history:
            prompt += "Lịch sử hội thoại:\n" + "\n".join(conversation_history) + "\n\n"
        
        prompt += "Hãy phân tích và hành động (Thought -> Action -> Final Answer):"
        
        # Call LLM
        response = provider.generate(prompt, system_prompt="")
        print(f"LLM Response:\n{response}")
        
        # Parse tool call from response
        tool_name, tool_args = parse_tool_call(response)
        
        if tool_name is None:
            # No tool call - LLM gave final answer
            print("Ket luan: LLM khong goi tool nao, tra loi truc tiep")
            conversation_history.append(f"LLM: {response}")
            trace.append({
                "iteration": iteration,
                "thought": extract_thought(response),
                "action": None,
                "observation": None,
                "final": True
            })
            break
        
        # Execute tool
        if tool_name not in AVAILABLE_TOOLS:
            observation = f"LỖI: Tool '{tool_name}' không tồn tại. Các tool khả dụng: {', '.join(AVAILABLE_TOOLS.keys())}"
        else:
            print(f"\n>>> Goi tool: {tool_name}({tool_args})")
            tool_func = AVAILABLE_TOOLS[tool_name]
            observation = tool_func(**tool_args)
        
        print(f"Observation: {observation}")
        
        # Add to history
        conversation_history.append(f"Thought: {extract_thought(response)}")
        conversation_history.append(f"Action: {tool_name}({tool_args})")
        conversation_history.append(f"Observation: {observation}")
        
        trace.append({
            "iteration": iteration,
            "thought": extract_thought(response),
            "action": f"{tool_name}({tool_args})",
            "observation": observation,
            "final": False
        })
        
        # Check if we should stop (tool returned critical error or "khong tim thay")
        if "KHÔNG ĐẠT" in observation or "LỖI:" in observation:
            print("Phat hien ket qua tu tool, chuan bi ket luan cuoi...")
    
    # Get final answer from LLM with all observations
    if iteration >= MAX_ITERATIONS:
        final_response = SAFE_FALLBACK_MESSAGE
    else:
        final_prompt = REACT_SYSTEM_PROMPT + "\n\n"
        final_prompt += f"Câu hỏi: {user_query}\n\n"
        final_prompt += "Lịch sử:\n" + "\n".join(conversation_history) + "\n\n"
        final_prompt += "Dua tren cac thong tin, hay dua ra ket luan cuoi cung (Final Answer):"
        final_response = provider.generate(final_prompt, system_prompt="")
    
    print(f"\n{'='*60}")
    print(f"Final Answer:\n{final_response}")
    print(f"{'='*60}")
    
    return {
        "question": user_query,
        "response": final_response,
        "trace": trace
    }


def parse_tool_call(response: str):
    """
    Parse tool call from LLM response.
    Supports formats: Action: tool_name[arg1, arg2] or Action: tool_name({"arg1": "value1"})
    
    Returns:
        tuple: (tool_name, kwargs_dict) or (None, None) if no tool call
    """
    import re
    
    # Look for Action: tool_name[args]
    pattern = r'Action:\s*(\w+)\[([^\]]+)\]'
    match = re.search(pattern, response, re.IGNORECASE)
    
    if match:
        tool_name = match.group(1)
        args_str = match.group(2)
        args = parse_arguments(args_str, tool_name)
        if args:
            return tool_name, args
    
    return None, None


def parse_arguments(args_str: str, tool_name: str = "") -> dict:
    """Parse tool arguments from string format."""
    import re
    args = {}
    
    # Clean up the string
    args_str = args_str.strip()
    
    # Try: screen_resume["Lê Văn C", "Frontend Developer"]
    # Extract quoted values directly
    pattern = r'["\']([^"\']+)["\']'
    matches = re.findall(pattern, args_str)
    
    if matches:
        parts = [m.strip() for m in matches]
        
        # screen_resume: candidate_name, position (2 args)
        if tool_name == "screen_resume" and len(parts) >= 2:
            args['candidate_name'] = parts[0]
            args['position'] = parts[1]
        
        # check_interviewer_availability: interviewer, date (2 args)
        elif tool_name == "check_interviewer_availability" and len(parts) >= 2:
            args['interviewer'] = parts[0]
            args['date'] = parts[1]
        
        # schedule_interview: candidate, interviewer, date, time (4 args)
        elif tool_name == "schedule_interview" and len(parts) >= 4:
            args['candidate_name'] = parts[0]
            args['interviewer'] = parts[1]
            args['date'] = parts[2]
            args['time'] = parts[3]
        
        # Fallback: detect tool from args_str content
        elif "screen" in args_str.lower() and len(parts) >= 2:
            args['candidate_name'] = parts[0]
            args['position'] = parts[1]
        elif "check" in args_str.lower() and len(parts) >= 2:
            args['interviewer'] = parts[0]
            args['date'] = parts[1]
        elif "schedule" in args_str.lower() and len(parts) >= 2:
            args['candidate_name'] = parts[0]
            if len(parts) >= 2:
                args['interviewer'] = parts[1]
            if len(parts) >= 3:
                args['date'] = parts[2]
            if len(parts) >= 4:
                args['time'] = parts[3]
    
    return args


def parse_json_arguments(args_str: str) -> dict:
    """Parse tool arguments from JSON-like string."""
    import re
    args = {}
    
    # Match "name": "value" patterns
    pattern = r'["\'](\w+)["\']\s*:\s*["\']([^"\']+)["\']'
    matches = re.findall(pattern, args_str)
    
    for name, value in matches:
        if name in ['candidate_name', 'candidate', 'name', 'interviewer', 'date', 'time', 'position']:
            args[name] = value
    
    return args


def extract_thought(response: str) -> str:
    """Extract Thought section from LLM response."""
    import re
    
    # Look for Thought: ... (until Action: or Final Answer)
    pattern = r'Thought:\s*(.+?)(?=Action:|Final Answer:|$)'
    match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
    
    if match:
        thought = match.group(1).strip()
        return thought[:500]  # Limit length
    
    # Fallback: first 200 chars
    return response[:200].strip()


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
    # DEMO: REACT AGENT - Chay tat ca test cases
    # ====================================================================
    print("\n" + "="*60)
    print("DEMO: REACT AGENT (Chay tat ca test cases)")
    print("="*60 + "\n")
    
    react_results = []
    
    for i, test in enumerate(tests):
        # Test ALL cases including edge case #5
        # if test['id'] == 5:
        #     print(f"\nTest Case #{test['id']} - [{test['category']}] - Skip for ReAct demo")
        #     continue
            
        print(f"\n{'='*60}")
        print(f"Test Case #{test['id']} - [{test['category']}]")
        print(f"{'='*60}")
        
        result = run_react_agent(test["question"], provider)
        react_results.append({
            "id": test["id"],
            "category": test["category"],
            "question": test["question"],
            "response": result["response"],
            "trace": result["trace"],
        })
    
    # Tom tat ket qua ReAct
    print("\n" + "="*60)
    print("TOM TAT KET QUA REACT AGENT")
    print("="*60)
    for r in react_results:
        print(f"\n  Test #{r['id']}: {r['category']}")
        for step in r['trace']:
            if step['action']:
                print(f"    - Iter {step['iteration']}: {step['action']} -> {'OK' if 'LỖI' not in str(step.get('observation', '')) else 'LỖI'}")
            else:
                print(f"    - Iter {step['iteration']}: Final Answer")
    
    print(f"\nHoan thanh ReAct Agent Demo!")
    print(f"Vui long xem trace_eval.md de ghi nhan ket qua.")
