from bs4 import BeautifulSoup
import requests
import time
import json
import os
import re
import logging
import sys

# ==========================================
# 1. CẤU HÌNH LOGGING (BẮN RA CẢ TERMINAL VÀ FILE)
# ==========================================
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler('scraper.log', encoding='utf-8'), # Ghi vào file
        logging.StreamHandler(sys.stdout)                     # In ra terminal
    ]
)

# ==========================================
# 2. CÁC HÀM XỬ LÝ ZBLL & DATA
# ==========================================
def clean_zbll_algs(algs):
    if not algs:
        return algs

    def simplify_moves(moves):
        def get_amount(move):
            if move.endswith("'") and move[:-1].endswith("2"): return 2
            if move.endswith("2"): return 2
            if move.endswith("'"): return 3
            return 1

        def get_base(move):
            base = move
            if base.endswith("'"): base = base[:-1]
            if base.endswith("2"): base = base[:-1]
            return base

        def is_prime_quarter(move):
            return move.endswith("'") and not move[:-1].endswith("2")

        def build_move(base, amount, prefer_prime_double=False):
            amount %= 4
            if amount == 0: return None
            if amount == 1: return base
            if amount == 2:
                if prefer_prime_double: return f"{base}2'"
                return f"{base}2"
            return f"{base}'"

        simplified = []
        for move in moves:
            if not simplified:
                simplified.append(move)
                continue

            last_move = simplified[-1]
            if get_base(last_move) == get_base(move):
                prefer_prime_double = is_prime_quarter(last_move) and is_prime_quarter(move)
                new_move = build_move(
                    get_base(move),
                    get_amount(last_move) + get_amount(move),
                    prefer_prime_double=prefer_prime_double
                )
                simplified.pop()
                if new_move:
                    simplified.append(new_move)
            else:
                simplified.append(move)

        return simplified

    algs = ' '.join(simplify_moves(algs.split()))
    
    leading_moves = []
    start_pattern = r"^(U2?'?)\s+"
    while True:
        match = re.match(start_pattern, algs)
        if not match: break
        leading_moves.append(f"({match.group(1)})")
        algs = re.sub(start_pattern, '', algs, count=1)
    
    end_pattern = r"\s+U2?'?$"
    while re.search(end_pattern, algs):
        algs = re.sub(end_pattern, '', algs, count=1)
    
    cleaned_algs = algs.strip()
    if leading_moves:
        if cleaned_algs:
            return f"{' '.join(leading_moves)} {cleaned_algs}"
        return ' '.join(leading_moves)
    return cleaned_algs

def get_solver_and_zbll(html_content, target_solvers):
    soup = BeautifulSoup(html_content, 'html.parser')
    solver_link = soup.find('a', id='solver-link')
    if not solver_link:
        return None, None
    
    solver_name = solver_link.get_text(strip=True)
    if solver_name not in target_solvers:
        return None, None 
    
    reconstruction_div = soup.find('div', id='reconstruction')
    if not reconstruction_div: 
        return solver_name, None
        
    lines = reconstruction_div.get_text('\n', strip=True).split('\n')
    for line in lines:
        if '// ZBLL' in line:
            return solver_name, clean_zbll_algs(line.split('//')[0].strip())
            
    return solver_name, None

# ==========================================
# 3. CÁC HÀM XỬ LÝ FILE (I/O)
# ==========================================
def init_storage(filepath):
    existing_ids = set()
    if not os.path.exists(filepath):
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("[]") 
    else:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                existing_ids = {item['id'] for item in data}
        except json.JSONDecodeError:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write("[]")
    return existing_ids

def append_to_json(filepath, new_entry):
    with open(filepath, 'r+', encoding='utf-8') as f:
        f.seek(0, os.SEEK_END)
        pos = f.tell() - 1
        while pos > 0:
            f.seek(pos)
            if f.read(1) == ']': break
            pos -= 1
            
        if pos > 0:
            f.seek(pos - 1)
            prev_char = f.read(1)
            f.seek(pos) 
            if prev_char != '[': f.write(',\n')
            json.dump(new_entry, f, ensure_ascii=False, indent=2)
            f.write('\n]')

def get_last_id(filepath="last_id.txt", default_start=1000):
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return int(f.read().strip())
    return default_start

def save_last_id(filepath, last_id):
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(str(last_id))

# ==========================================
# 4. HÀM CRAWL CHÍNH
# ==========================================
def crawl_reco_multi(start_id, end_id, target_solvers, delay=0.5):
    base_url = "https://reco.nz/solve/"
    
    processed_ids_map = {}
    for solver in target_solvers:
        filename = f"{solver.replace(' ', '_')}_zbll_algs.json"
        processed_ids_map[solver] = init_storage(filename)
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    session = requests.Session()
    session.headers.update(headers)
    total = end_id - start_id + 1

    logging.info(f"Bắt đầu cào {len(target_solvers)} người chơi từ ID {start_id} đến {end_id}...")

    # [MỚI] Khởi tạo biến lưu ID hợp lệ cuối cùng
    last_valid_id = start_id - 1 

    for solve_id in range(start_id, end_id + 1):
        url = f"{base_url}{solve_id}"
        current = solve_id - start_id + 1
        
        try:
            response = session.get(url, timeout=10)
            
            if response.status_code == 429:
                logging.warning(f"[{current}/{total}] ID {solve_id}: Dính 429 Too Many Requests! Đang ngủ 60s...")
                time.sleep(60)
                continue 
                
            if response.status_code == 404:
                # [MỚI] Gặp 404 là dừng luôn vòng lặp, đã chạm đỉnh ID web
                logging.info(f"[{current}/{total}] ID {solve_id}: 404 Not found -> Chạm đỉnh ID của web. DỪNG CÀO!")
                break
            
            response.raise_for_status()
            
            # [MỚI] Nếu chạy tới đây không lỗi lầm gì, cập nhật ID hợp lệ cuối cùng
            last_valid_id = solve_id
            
            solver_name, zbll = get_solver_and_zbll(response.text, target_solvers)
            
            if solver_name and zbll:
                if solve_id not in processed_ids_map[solver_name]:
                    new_entry = {'id': solve_id, 'url': url, 'zbll': zbll}
                    filename = f"{solver_name.replace(' ', '_')}_zbll_algs.json"
                    
                    append_to_json(filename, new_entry)
                    processed_ids_map[solver_name].add(solve_id)
                    logging.info(f"[{current}/{total}] ID {solve_id}: FOUND {solver_name} - {zbll}")
                else:
                    # ---> FIX Ở ĐÂY: Thêm - {zbll} vào đuôi <---
                    logging.info(f"[{current}/{total}] ID {solve_id}: Đã có {solver_name} - {zbll}")
            else:
                logging.info(f"[{current}/{total}] ID {solve_id}: Skip")
            
        except requests.exceptions.Timeout:
            logging.warning(f"[{current}/{total}] ID {solve_id}: Timeout, server phản hồi chậm.")
        except Exception as e:
            logging.error(f"[{current}/{total}] ID {solve_id}: Lỗi không xác định - {e}")
        
        time.sleep(delay)

    # [MỚI] Trả về ID hợp lệ để ở dưới lưu lại
    return last_valid_id

# ==========================================
# 5. EXECUTION BLOCK
# ==========================================
if __name__ == '__main__':
    danh_sach_vip = [
        "Tymon Kolasiński", 
        "Xuanyi Geng", 
        "Bofan Zhang",
        "Qixian Cao",
    ]
    
    last_id = get_last_id("last_id.txt", default_start=12638)
    
    start_id = last_id + 1
    # Ông có thể set offset cao hẳn lên (VD: 500) vì đằng nào gặp 404 nó cũng tự thắng gấp
    offset = 500 
    end_id = start_id + offset
    
    # [MỚI] Lấy kết quả trả về của hàm để biết dừng ở ID nào
    actual_last_id = crawl_reco_multi(
        start_id=start_id,
        end_id=end_id,
        target_solvers=danh_sach_vip,
        delay=0.5
    )
    
    # [MỚI] Lưu mốc ID thực tế
    save_last_id("last_id.txt", actual_last_id)
    logging.info(f"Đã chạy xong! Lưu mốc ID mới cho tuần sau: {actual_last_id}.")