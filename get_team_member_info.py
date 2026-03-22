import sys
import requests
import re
import time
import random
from bs4 import BeautifulSoup
from datetime import datetime

# === 配置区域 ===
# 1. 在这里粘贴你从浏览器开发者工具复制的完整 Cookie
MY_COOKIE = "__cmpcc=1; _pubcid=0cf3d892-a035-4cc3-a0dd-2c5d1780c59a; __vads=kxcmIK4an4WlwnPxF1go1O575; __cmpconsentx47074=CQhALZgQhALZgAfQyBENCWFgAP_AAEPAAAigKVlR9G5dTWFBeTJ3YJskeYQX0chpZkABAgaAAyABCDGAYIQEkkEyIAyAAAACARAAoDSBAAAgDAhEAEAAAIgBAADoAAAEgBAIIAAEABERQ0IAAAgKCIgAEAAIAAB1IkAAkAKAAJLiQNAAgIAiAAABAAAAAIABAAMAAAAIAAACAAIAQAAAAAAAgAAAAAACARAIAAAAAAAAIAAAAAAAAAAAAAAAAAAAAACCN4AJBoVEEBQEAAQCABBAgAEFAAAUAAAAAEgAIAAAgQAGAEABBBMgAAAAAAAAEAAIAAAQAAAAAIRABAAACAAAAAKAAAAAAACAAAAAAQAUIAAAAICgCIAAAAAAAARCBAAIAAAAAQAkBQAAAAIAAAAAAAAACAAAAAAAAACAAAAAAAAAAAAAAAAIAAAAAAAAAACAAA.IKVlR9G5dTWFBeTJ3YJskeYQX0chpZkABAgaAAyABCDGAYIQEkkEyIAyAAAACARAAoDSBAAAgDAhEAEAAAIgBAADoAAAEgBAIIAAEABERQ0IAAAgKCIgAEAAIAAB1IkAAkAKAAJLiQNAAgIAiAAABAAAAAIABAAMAAAAIAAACAAIAQAAAAAAAgAAAAAACARAIAAAAAAAAIAAAAAAAAAAAAAAAAAAAAAC.f_gACHgAAAA; __cmpcccx47074=aCQhCU1zgAAs_WGaaxrDMcjwrJgyOeIZjLU0NVlqZDgeYsSwLFghqZWKmkzABlcXqxaRkjE1MMkaLWpkwYyamrJDQwMmWGU1GTQxYGiYMGWLGpYZELQTFgmFqgxVhGIZKGAA; pbjs-unifiedid=%7B%22TDID_LOOKUP%22%3A%22FALSE%22%2C%22TDID_CREATED_AT%22%3A%222026-03-13T14%3A38%3A17%22%7D; pbjs-unifiedid_cst=qixOLLksfQ%3D%3D; __mggpc__=0; panoramaId_expiry=1774209199267; sb-10-auth-token=base64-eyJhY2Nlc3NfdG9rZW4iOiJleUpoYkdjaU9pSklVekkxTmlJc0luUjVjQ0k2SWtwWFZDSjkuZXlKemRXSWlPaUpsWkRrM09EZGpPQzFqWlRKa0xUUmtORGd0T1dNNE5pMDRNR0V3WWpRNE5HWmlNekVpTENKaGRXUWlPaUpoZFhSb1pXNTBhV05oZEdWa0lpd2laWGh3SWpveE56YzBNVE0zTkRFMkxDSnBZWFFpT2pFM056UXhNek00TVRZc0ltVnRZV2xzSWpvaVptVnVaeTUzWVc1bmMwQm5iV0ZwYkM1amIyMGlMQ0p3YUc5dVpTSTZJaUlzSW1Gd2NGOXRaWFJoWkdGMFlTSTZleUp3Y205MmFXUmxjaUk2SW1WdFlXbHNJaXdpY0hKdmRtbGtaWEp6SWpwYkltVnRZV2xzSWwxOUxDSjFjMlZ5WDIxbGRHRmtZWFJoSWpwN2ZTd2ljbTlzWlNJNkltRjFkR2hsYm5ScFkyRjBaV1FpTENKaFlXd2lPaUpoWVd3eElpd2lZVzF5SWpwYmV5SnRaWFJvYjJRaU9pSndZWE56ZDI5eVpDSXNJblJwYldWemRHRnRjQ0k2TVRjM05ERXlOekl5Tm4xZExDSnpaWE56YVc5dVgybGtJam9pT0RCaU16ZGpNbUl0TjJaak1pMDBNVGd4TFdJNVpETXRPVGhpT0Rjd00yTTROakl4SWl3aWFYTmZZVzV2Ym5sdGIzVnpJanBtWVd4elpYMC5Ob0xlNXRzUTZ6UW55TEZmSlQyS29QTlhTU0ZweG9ueWF4QmFaSDZseEtjIiwidG9rZW5fdHlwZSI6ImJlYXJlciIsImV4cGlyZXNfaW4iOjM2MDAsImV4cGlyZXNfYXQiOjE3NzQxMzc0MTYsInJlZnJlc2hfdG9rZW4iOiJmNzZlZHhiY2ludGIiLCJ1c2VyIjp7ImlkIjoiZWQ5Nzg3YzgtY2UyZC00ZDQ4LTljODYtODBhMGI0ODRmYjMxIiwiYXVkIjoiYXV0aGVudGljYXRlZCIsInJvbGUiOiJhdXRoZW50aWNhdGVkIiwiZW1haWwiOiJmZW5nLndhbmdzQGdtYWlsLmNvbSIsImVtYWlsX2NvbmZpcm1lZF9hdCI6IjIwMTYtMTAtMjBUMjI6MjY6MDBaIiwicGhvbmUiOiIiLCJjb25maXJtYXRpb25fc2VudF9hdCI6IjIwMTYtMTAtMjBUMjI6MjQ6MDBaIiwiY29uZmlybWVkX2F0IjoiMjAxNi0xMC0yMFQyMjoyNjowMFoiLCJsYXN0X3NpZ25faW5fYXQiOiIyMDI2LTAzLTIxVDIxOjA3OjA2LjgxMTIzOFoiLCJhcHBfbWV0YWRhdGEiOnsicHJvdmlkZXIiOiJlbWFpbCIsInByb3ZpZGVycyI6WyJlbWFpbCJdfSwidXNlcl9tZXRhZGF0YSI6e30sImlkZW50aXRpZXMiOlt7ImlkZW50aXR5X2lkIjoiNDdmMzU0ZTItMjg1ZS00OWI2LWI4Y2ItMDA2ZWZjMjUwYzk4IiwiaWQiOiJlZDk3ODdjOC1jZTJkLTRkNDgtOWM4Ni04MGEwYjQ4NGZiMzEiLCJ1c2VyX2lkIjoiZWQ5Nzg3YzgtY2UyZC00ZDQ4LTljODYtODBhMGI0ODRmYjMxIiwiaWRlbnRpdHlfZGF0YSI6eyJlbWFpbCI6ImZlbmcud2FuZ3NAZ21haWwuY29tIiwiZW1haWxfdmVyaWZpZWQiOmZhbHNlLCJwaG9uZV92ZXJpZmllZCI6ZmFsc2UsInN1YiI6ImVkOTc4N2M4LWNlMmQtNGQ0OC05Yzg2LTgwYTBiNDg0ZmIzMSJ9LCJwcm92aWRlciI6ImVtYWlsIiwiY3JlYXRlZF9hdCI6IjIwMTYtMTAtMjBUMjI6MjQ6MDBaIiwidXBkYXRlZF9hdCI6IjIwMTYtMTAtMjBUMjI6MjQ6MDBaIiwiZW1haWwiOiJmZW5nLndhbmdzQGdtYWlsLmNvbSJ9XSwiY3JlYXRlZF9hdCI6IjIwMTYtMTAtMjBUMjI6MjQ6MDBaIiwidXBkYXRlZF9hdCI6IjIwMjYtMDMtMjFUMjI6NTY6NTYuMDg3MjU3WiIsImlzX2Fub255bW91cyI6ZmFsc2V9fQ; emqsegs=e0,e2pb,e3np,e1ff,e2p7,e3o,e3nm,e2p3,e3pp,e2h7,e2pm,e2p1,e3q6,e2pi,e3nj,e3o2,e3q4,eud,e2v9,e1gs,e2p4,e3nq,e363,e3ym,e2p0,e2c,e2pj,e12b,e2pf,e3oe,e3ot,e3z2,e3yl,e1,e2s8,e2oz,e3nr,e2s4,e2pg,e1ri,e2pe,e3o7,e3zp,e2pa,e2p2,e2rc,e3yk,e3a,ezz,e3i,e30c,e2pd,e3ng,e3yi,e2oy,e3pl,eyv,e2po,ea,e3pj,e2pc,e2p8,e2vv,e121,e2ox,e3pb,e2pn,e2re,e3pi,e3ns,e2p9,e3od,e2p5,e3m,e35,e2gs,e2v6,e2pk,e3ud,e3o0,e56,e37z,e2pp,e3o4; _pubcid_cst=qk65fQ%3D%3D; _tfpvi=ZjBjYjE4NzgtMGI3Mi00NzhjLWE2ODUtZmUzZmFjZmU3OTJkIy04LTM%3D; cto_bidid=gyyks192UGlWSjdtZmlNcWtkczViRDdrampIVjZFSEt3YUJPc2VtU2FDcmN0dnlnZzEwOWxrSyUyQnNaamlid2xlTVQlMkYxSXprUHFBcXUxNzdwc1pkdlZmZ2JqT0dKNUxrU1VwaXl2bWM2RTNXOVJ0RFB0ZDR0NzVmaVpuMzdLa1dEUzlqWGV0VW9MYXFMTmZNejNEdFMlMkYxT1ZodnclM0QlM0Q; cto_bundle=iCt3BF9WdTBHVGdpVjFSUXc2RmVBVmc2T3l4eGpJZXB2NU1xV3ozT05QNUpocjRoREl4ZmJSNGw4MmFmRHNxMjRNeGNnbEFSN0tzJTJGZ3JRQXF4U1ZMZml1T1hDN1VZREt3N1pvNHBuWldPVmJqOFFxV0dDNmtScVBpMWMyYmxoYlUxUHA2SkxlJTJCaVk4Qzg5blliM0NEYm9oWDYlMkJZbWJoYlQwSlFLRkxLJTJGU1RUVEJGa2Jhb2xva3pSRlZIJTJCJTJCRnIyUCUyQkU0bA; __gads=ID=2a6cb4d748e46ac7:T=1770495753:RT=1774134515:S=ALNI_MbvEhR60lRyY-tNcl12va8V8UN83A; __gpi=UID=000012f16bb25446:T=1770495753:RT=1774134515:S=ALNI_Mb4FHDYGTLMBJdLsb1PaUCoeRVveQ; __eoi=ID=f558dc6b1e68af3b:T=1770495753:RT=1774134515:S=AA-AfjYH9hwp7AiRSCZ924GR-Bog"

# 2. 模拟真实浏览器的 Headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "Cookie": MY_COOKIE,
    "Referer": "https://www.mytischtennis.de/"
}

team_id = sys.argv[1] if len(sys.argv) > 1 else "2958172"
url = f"https://www.mytischtennis.de/click-tt/TTBW/25--26/ligen/Erwachsene_Kreisliga_A_Gr._2/gruppe/494310/mannschaft/{team_id}/TV_Zuffenhausen_III/spielerbilanzen/gesamt"

# 创建 Session 自动管理会话
session = requests.Session()
session.headers.update(HEADERS)
def get_individual_ttr(portrait_url):
    """基于截图特征的精准定位版"""
    if not portrait_url:
        return "N/A", "N/A"
    
    try:
        # 增加一点延迟，确保安全
        time.sleep(random.uniform(1.2, 2.0))
        p_resp = session.get(portrait_url, timeout=10)
        soup = BeautifulSoup(p_resp.text, "html.parser")
        
        q_ttr = "N/A"
        current_ttr = "N/A"

        # 策略：在 myTischtennis 登录后的个人主页中，
        # TTR 数字通常被包裹在 class 包含 'rating-value' 或在大标题下。
        # 结合截图，我们直接寻找所有 3-4 位的纯数字文本块。

        # 1. 查找所有可能包含数字的 div
        # 登录后 TTR 数字通常是页面中字体最大的数字
        # 我们寻找紧跟在 "Q-TTR-Wert" 和 "TTR-Wert" 标识之后的数字
        
        # 寻找 Q-TTR
        q_header = soup.find(string=re.compile(r'Q-TTR-Wert'))
        if q_header:
            # 找到标签后，搜索它之后最近的一个 3-4 位数字
            # 这种方法无视层级嵌套，只要逻辑顺序对就行
            following_text = "".join([s for s in q_header.parent.parent.stripped_strings])
            nums = re.findall(r'\d{3,4}', following_text)
            if nums:
                q_ttr = nums[0]

        # 寻找 实时 TTR (排除掉 Q-TTR 干扰)
        t_headers = soup.find_all(string=re.compile(r'TTR-Wert'))
        for t_header in t_headers:
            if "Q-TTR" not in t_header:
                following_text = "".join([s for s in t_header.parent.parent.stripped_strings])
                nums = re.findall(r'\d{3,4}', following_text)
                if nums:
                    current_ttr = nums[0]
                    break

        # 2. 如果还是没抓到，使用截图展示的“物理顺序”抓取
        if q_ttr == "N/A" or current_ttr == "N/A":
            # 查找页面中所有 > 800 的数字（过滤掉杂碎数字）
            all_text = soup.get_text(separator=' ')
            # 寻找类似 "Q-TTR-Wert 1523" 这种结构的文本
            matches = re.findall(r'(?:Q-TTR-Wert|TTR-Wert)\s*(\d{3,4})', all_text)
            if len(matches) >= 2:
                q_ttr, current_ttr = matches[0], matches[1]
            elif len(matches) == 1:
                q_ttr = current_ttr = matches[0]

        return q_ttr, current_ttr
    except Exception as e:
        return "Err", "Err"
# --- 开始执行 ---
print(f"🚀 正在获取 teamId = {team_id} 的数据...")

try:
    response = session.get(url, timeout=15)
    soup = BeautifulSoup(response.text, "html.parser")
    
    print(f"\n# 📊 球员实时 TTR 信息表（{datetime.now().strftime('%Y-%m-%d %H:%M')}）")
    print("\n| 位置 | 姓名 | 出场/胜负 | Q-TTR | 实时 TTR |")
    print("|------|------|----------|-------|----------|")

    rows = soup.select("table tr")
    count = 0
    
    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 8: continue
        
        position = cols[0].get_text(strip=True)
        # 过滤日期行或无效行
        if any(d in position for d in ["Mo.", "Di.", "Mi.", "Do.", "Fr.", "Sa.", "So."]): continue
        if not ("." in position): continue

        name_tag = cols[1].find("a")
        name = name_tag.get_text(strip=True) if name_tag else cols[1].get_text(strip=True)
        matches = cols[2].get_text(strip=True)
        record = cols[7].get_text(strip=True)

        # 获取详情页链接
        portrait_path = name_tag["href"] if name_tag and name_tag.has_attr("href") else ""
        portrait_url = "https://www.mytischtennis.de" + portrait_path if portrait_path else ""
        
        # 抓取个人 TTR
        q_val, t_val = get_individual_ttr(portrait_url)
        
        print(f"| {position} | {name} | {matches} / {record} | {q_val} | {t_val} |")
        count += 1

    print(f"\n✅ 处理完成，共计 {count} 名球员。")

except Exception as e:
    print(f"❌ 运行出错: {e}")
