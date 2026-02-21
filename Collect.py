from bs4 import BeautifulSoup
import requests
import time
import json
import os


import re


def clean_zbll_algs(algs):
    if not algs:
        return algs
    
    # Remove U, U', U2, U2' from the START
    start_pattern = r"^U2?'?\s+"
    while re.match(start_pattern, algs):
        algs = re.sub(start_pattern, '', algs, count=1)
    
    # Remove U, U', U2, U2' from the END
    end_pattern = r"\s+U2?'?$"
    while re.search(end_pattern, algs):
        algs = re.sub(end_pattern, '', algs, count=1)
    
    return algs.strip()


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
    