from bs4 import BeautifulSoup
import requests
import time
import json
import os


import re


def clean_zbll_algs(algs):
    if not algs:
        return algs

    def simplify_moves(moves):
        def get_amount(move):
            if move.endswith("'") and move[:-1].endswith("2"):
                return 2
            if move.endswith("2"):
                return 2
            if move.endswith("'"):
                return 3
            return 1

        def get_base(move):
            base = move
            if base.endswith("'"):
                base = base[:-1]
            if base.endswith("2"):
                base = base[:-1]
            return base

        def is_prime_quarter(move):
            return move.endswith("'") and not move[:-1].endswith("2")

        def build_move(base, amount, prefer_prime_double=False):
            amount %= 4
            if amount == 0:
                return None
            if amount == 1:
                return base
            if amount == 2:
                if prefer_prime_double:
                    return f"{base}2'"
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
    
    # Wrap leading U, U', U2, U2' in parentheses instead of removing
    leading_moves = []
    start_pattern = r"^(U2?'?)\s+"
    while True:
        match = re.match(start_pattern, algs)
        if not match:
            break
        leading_moves.append(f"({match.group(1)})")
        algs = re.sub(start_pattern, '', algs, count=1)
    
    # Remove U, U', U2, U2' from the END
    end_pattern = r"\s+U2?'?$"
    while re.search(end_pattern, algs):
        algs = re.sub(end_pattern, '', algs, count=1)
    
    cleaned_algs = algs.strip()
    if leading_moves:
        if cleaned_algs:
            return f"{' '.join(leading_moves)} {cleaned_algs}"
        return ' '.join(leading_moves)
    return cleaned_algs


def get_zbll_algs(html_content, target_solver="Tymon Kolasiński"):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Check solver name from #solver-link
    solver_link = soup.find('a', id='solver-link')
    if not solver_link:
        return None
    
    solver_name = solver_link.get_text(strip=True)
    if solver_name != target_solver:
        return None
    
    # Extract ZBLL algs from #reconstruction div
    reconstruction_div = soup.find('div', id='reconstruction')
    if not reconstruction_div:
        return None
    
    # Get all lines and find ZBLL step
    lines = reconstruction_div.get_text('\n', strip=True).split('\n')
    lines = [line.strip() for line in lines if line.strip()]
    
    for line in lines:
        if '// ZBLL' in line:
            # Extract just the moves (before //)
            moves = line.split('//')[0].strip()
            # Remove leading U, U', U2, U2'
            return clean_zbll_algs(moves)
    
    return None


def get_zbll_from_file(filepath, target_solver="Tymon Kolasiński"):
    """Get ZBLL algs from a local HTML file"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return get_zbll_algs(f.read(), target_solver)


def get_zbll_from_url(url, target_solver="Tymon Kolasiński"):
    """Fetch URL and get ZBLL algs"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    return get_zbll_algs(response.text, target_solver)


def crawl_reco_range(start_id, end_id, target_solver="Tymon Kolasiński", delay=0.5, output_file="zbll_results.json"):
    base_url = "https://reco.nz/solve/"
    results = []
    
    # Load existing results if file exists (to resume)
    processed_ids = set()
    if os.path.exists(output_file):
        with open(output_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
            processed_ids = {r['id'] for r in results}
            print(f"Loaded {len(results)} existing results, resuming...")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    total = end_id - start_id + 1
    found_count = len(results)
    
    for solve_id in range(start_id, end_id + 1):
        # Skip if already processed
        if solve_id in processed_ids:
            continue
        
        url = f"{base_url}{solve_id}"
        current = solve_id - start_id + 1
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 404:
                print(f"[{current}/{total}] ID {solve_id}: Not found")
                time.sleep(delay / 2)
                continue
            
            response.raise_for_status()
            zbll = get_zbll_algs(response.text, target_solver)
            
            if zbll:
                results.append({
                    'id': solve_id,
                    'url': url,
                    'zbll': zbll
                })
                found_count += 1
                print(f"[{current}/{total}] ID {solve_id}: FOUND - {zbll}")
                
                # Save progress every 10 finds
                if found_count % 10 == 0:
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(results, f, ensure_ascii=False, indent=2)
            else:
                print(f"[{current}/{total}] ID {solve_id}: No match")
            
        except requests.exceptions.Timeout:
            print(f"[{current}/{total}] ID {solve_id}: Timeout")
        except requests.exceptions.RequestException as e:
            print(f"[{current}/{total}] ID {solve_id}: Error - {e}")
        
        time.sleep(delay)
    
    # Final save
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*50}")
    print(f"Crawling complete!")
    print(f"Total ZBLL algs found: {len(results)}")
    print(f"Results saved to: {output_file}")
    
    return results


if __name__ == '__main__':
    target_solver = "Xuanyi Geng"
    results = crawl_reco_range(
        start_id=10044,
        end_id=12630,
        target_solver=target_solver,
        delay=0.5,
        output_file=f"{target_solver}_zbll_algs.json"
    )
    