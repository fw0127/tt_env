import sys
import requests
import re

def search_teamid(team_query):
    print(f"🔍 正在搜索队名: {team_query}")
    
    # 智能提取俱乐部名字 (SKG Gablenberg IV -> SKG Gablenberg)
    club_query = re.sub(r'\s+([IVX]+|\d+)$', '', team_query, flags=re.IGNORECASE).strip()
    print(f"🏢 提取到的俱乐部名称: {club_query}")
    
    # 1. 搜索俱乐部
    club_url = "https://www.mytischtennis.de/api/search/clubs"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    
    try:
        # 【关键修复】：改回使用 data= 传参，避免服务器 500 崩溃
        club_resp = requests.post(
            club_url,
            data={"query": club_query, "page": 1, "pagesize": 5},
            headers=headers,
            timeout=10
        )
        
        print(f"🛠️ [调试] 俱乐部接口 HTTP 状态码: {club_resp.status_code}")
        
        if club_resp.status_code != 200:
            print(f"❌ 服务器返回异常状态: {club_resp.status_code}")
            return None
            
        clubs = club_resp.json().get("results", [])
        
    except requests.exceptions.JSONDecodeError:
        print("❌ 无法解析返回数据，网站可能开启了人机验证(Captcha)拦截。")
        return None
    except Exception as e:
        print(f"❌ 请求发生异常: {e}")
        return None
    
    if not clubs:
        print("❌ 未找到任何俱乐部")
        return None
        
    # 取第一个最匹配的俱乐部
    club = clubs[0]
    club_nr = club.get("clubnr")
    org = club.get("organization_short", "TTBW")
    print(f"✅ 找到俱乐部: {club.get('clubname', '未知')} (clubnr={club_nr}, org={org})")
    
    # 2. 获取该俱乐部所有队伍
    teams_url = f"https://www.mytischtennis.de/api/ttr/teams?clubNumber={club_nr}&organization={org}"
    
    try:
        teams_resp = requests.get(teams_url, headers=headers, timeout=10)
        teams_data = teams_resp.json().get("data", [])
    except Exception as e:
        print(f"❌ 获取队伍列表时发生异常: {e}")
        return None
    
    # 3. 模糊匹配队名
    query_lower = team_query.lower().replace(" ", "").replace("iii", "3").replace("iv", "4")
    best_match = None
    best_score = 0
    
    for team in teams_data:
        team_name = team.get("team_name", "").lower().replace(" ", "")
        score = sum(1 for char in query_lower if char in team_name)
        if score > best_score:
            best_score = score
            best_match = team
            
    if not best_match:
        print("❌ 未找到匹配的队伍")
        return None
        
    team_id = best_match.get("team_id")
    team_full_name = best_match.get("team_name")
    
    print("✅ 匹配成功！")
    print(f"队伍名称: {team_full_name}")
    print(f"teamId: {team_id}")
    print(f"organization: {org}")
    
    return team_id

if __name__ == "__main__":
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        query = input("请输入队名（例如 TV Zuffenhausen III 或 SKG Gablenberg IV）: ")
        
    search_teamid(query)
