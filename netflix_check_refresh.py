#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import subprocess
import time
import sys
import shlex # 用于安全处理命令 (虽然在此版本中未直接使用 shlex.split，但保留以备将来可能需要)

# --- 配置区域 ---
# 目标 Netflix 页面 (ID 70143836 对应《低俗小说》, sg-zh 尝试获取新加坡简体中文版页面)
NETFLIX_URL = "https://www.netflix.com/sg-zh/title/70143836"

# 需要查找的确切限制信息文本
FAILURE_STRING = "糟糕！此作品目前无法在您的国家/地区观赏。"

# Cloudflare WARP IPv6 刷新命令 (参数 '6' 通常用于获取IPv6)
WARP_COMMAND_STRING = "bash <(curl -fsSL https://raw.githubusercontent.com/P3TERX/warp.sh/main/warp.sh) 6"

# 循环控制参数
MAX_RETRIES = 20  # 最多尝试多少次 (包括IP刷新后的重试)
RETRY_DELAY_SECONDS = 15 # 每次IP刷新或一般重试后等待多少秒
REQUEST_TIMEOUT_SECONDS = 25 # 访问 Netflix 页面的超时时间
IP_CHECK_TIMEOUT_SECONDS = 10 # 获取公网IP的超时时间

# 模拟浏览器的 Headers
HTTP_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.127 Safari/537.36',
    'Accept-Language': 'zh-SG,zh;q=0.9,en-US;q=0.8,en;q=0.7', # 匹配 sg-zh 路径
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'Referer': 'https://www.google.com/'
}
# --- 配置结束 ---

def get_current_public_ipv6(timeout_seconds=IP_CHECK_TIMEOUT_SECONDS):
    """获取当前机器的公网 IPv6 地址。"""
    # 尝试多个服务获取IP，增加成功率
    ip_services = [
        "https://api64.ipify.org",
        "https://ifconfig.me/ip", # ifconfig.me有时会返回非IP内容，但/ip路径应该还好
        "https://icanhazip.com",
        "https://ipinfo.io/ip"
    ]
    
    for service_url in ip_services:
        # -6: 强制使用IPv6
        # --fail: HTTP错误时静默失败 (返回非0退出码)
        # --silent: 不显示进度条
        # --show-error: 即使有-s，也显示错误
        # --connect-timeout: 连接超时
        # --max-time: 总操作超时
        command = [
            'curl', '-6', '--fail', '--silent', '--show-error',
            '--connect-timeout', str(timeout_seconds // 2), # 分配部分超时给连接
            '--max-time', str(timeout_seconds),
            service_url
        ]
        try:
            # 为整个subprocess调用也设置一个超时，以防curl卡死
            process = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout_seconds + 5)
            if process.returncode == 0 and process.stdout.strip():
                ipv6_address = process.stdout.strip()
                # 简单验证是否像IPv6地址 (包含':', 不含'.')
                if ':' in ipv6_address and '.' not in ipv6_address:
                    return ipv6_address
                else:
                    print(f"   [IP获取调试] 从 {service_url} 获取的内容 \"{ipv6_address}\" 看不像有效的IPv6。")
            # else: # 调试时可以取消注释看详细错误
            #     print(f"   [IP获取调试] 从 {service_url} 获取IPv6失败。返回码: {process.returncode}, STDOUT: '{process.stdout.strip()}', STDERR: '{process.stderr.strip()}'")
        except subprocess.TimeoutExpired:
            # print(f"   [IP获取调试] 从 {service_url} 获取IPv6超时。")
            pass # 超时则尝试下一个服务
        except Exception as e:
            # print(f"   [IP获取调试] 从 {service_url} 获取IPv6时发生异常: {e}")
            pass # 发生其他异常也尝试下一个服务
            
    return None # 所有服务都失败

def run_warp_refresh(attempt_info_str):
    """执行 WARP IPv6 刷新命令并处理输出"""
    print(f"--- {attempt_info_str} 检测到问题，开始执行 WARP IPv6 刷新 ---")
    try:
        process = subprocess.run(
            ['bash', '-c', WARP_COMMAND_STRING],
            check=False,
            capture_output=True,
            text=True,
            timeout=180  # 为 WARP 脚本设置较长超时 (3 分钟)
        )

        print("--- WARP 命令 STDOUT ---")
        print(process.stdout if process.stdout.strip() else "(无标准输出)")
        print("--- WARP 命令 STDERR ---")
        print(process.stderr if process.stderr.strip() else "(无标准错误输出)")

        if process.returncode == 0:
            print(f"--- WARP 刷新命令似乎执行成功 (退出码: {process.returncode}) ---")
        else:
            print(f"--- WARP 刷新命令执行失败 (退出码: {process.returncode}) ---")
            if process.stderr:
                # warp.sh 脚本通常会将主要错误信息输出到 stdout，但这里也检查 stderr
                print(f"   提示: 请检查上面的STDOUT和STDERR获取详细的WARP脚本错误信息。")

    except subprocess.TimeoutExpired:
        print("--- WARP 刷新命令执行超时 ---")
    except Exception as e:
        print(f"--- 执行 WARP 刷新时发生 Python 异常: {e} ---")

# --- 主程序逻辑 ---
print("--- 开始 Netflix 解锁状态检查与自动刷新循环 ---")
print(f"目标页面: {NETFLIX_URL}")
print(f"查找限制信息: \"{FAILURE_STRING}\"")
print(f"最大尝试次数: {MAX_RETRIES}")

retries_done = 0
while retries_done < MAX_RETRIES:
    current_attempt_num = retries_done + 1
    attempt_info = f"[尝试 {current_attempt_num}/{MAX_RETRIES}]"
    print(f"\n--- {attempt_info} ---")

    # 1. 获取并打印当前公网 IPv6
    print("正在获取当前公网 IPv6 地址...")
    current_ipv6 = get_current_public_ipv6()
    if current_ipv6:
        print(f"当前公网 IPv6 地址: {current_ipv6}")
    else:
        print("未能获取当前公网 IPv6 地址或当前无IPv6出口。")

    # 标志位，决定本次循环后是否需要刷新IP
    trigger_ip_refresh = False
    netflix_check_successful = False

    try:
        print(f"正在访问 Netflix: {NETFLIX_URL} ...")
        response = requests.get(
            NETFLIX_URL,
            headers=HTTP_HEADERS,
            timeout=REQUEST_TIMEOUT_SECONDS
        )
        print(f"页面 HTTP 状态码: {response.status_code}")
        response.raise_for_status() # 如果状态码不是 2xx，会抛出 HTTPError 异常

        page_content = response.text
        if FAILURE_STRING in page_content:
            print(f"❌ {attempt_info} 找到限制信息: \"{FAILURE_STRING}\"")
            trigger_ip_refresh = True
        else:
            print(f"✅ {attempt_info} 未在页面找到预设的限制信息 \"{FAILURE_STRING}\"。")
            print("--- 页面部分内容预览 (用于判断解锁状态或不同错误信息) ---")
            preview_length = 500
            print(page_content[:preview_length] + "..." if len(page_content) > preview_length else page_content)
            print("----------------------------------------------------")
            print("假定已解锁！")
            print("--- 脚本成功结束 ---")
            netflix_check_successful = True # 设置成功标志
            sys.exit(0) # 正常退出

    except requests.exceptions.HTTPError as e:
        print(f"错误：HTTP 错误 - {e}")
        # 对于特定的客户端或服务器错误，我们尝试刷新IP
        # 403: Forbidden (IP被禁), 404: Not Found (IP被禁或内容URL问题), 429: Too Many Requests
        # 5xx: Server errors (有时也可能与客户端IP信誉有关或服务不稳定)
        if e.response.status_code in [403, 404, 429, 500, 502, 503, 504]:
            print(f"   {attempt_info} 此类HTTP错误({e.response.status_code})通常表示IP问题或Netflix服务问题，将尝试刷新IP。")
            trigger_ip_refresh = True
        else:
            print(f"   {attempt_info} 遇到非严重HTTP错误({e.response.status_code})，将等待后重试（不立即刷新IP）。")
            # 如果希望所有HTTP错误都刷新IP，此处也设置 trigger_ip_refresh = True

    except requests.exceptions.Timeout:
        print(f"错误：{attempt_info} 访问 Netflix 超时 (超过 {REQUEST_TIMEOUT_SECONDS} 秒)。")
        print("   访问超时可能与当前IP或网络路由有关，将尝试刷新IP。")
        trigger_ip_refresh = True
        
    except requests.exceptions.ConnectionError as e: # 更具体的连接错误
        print(f"错误：{attempt_info} 连接错误 - {e}")
        print("   连接错误可能与当前IP或网络路由有关，将尝试刷新IP。")
        trigger_ip_refresh = True

    except requests.exceptions.RequestException as e: # 其他 requests 库的异常
        print(f"错误：{attempt_info} 网络请求相关错误 - {e}")
        print("   此类网络问题也可能从IP刷新中受益，将尝试刷新IP。")
        trigger_ip_refresh = True
        
    except Exception as e:
        print(f"发生未知 Python 错误: {e}")
        print(f"   {attempt_info} 未知错误，为排除网络因素，将尝试刷新IP。")
        trigger_ip_refresh = True
    
    # --- 执行IP刷新或等待 ---
    if not netflix_check_successful: # 如果上面没有成功退出
        retries_done += 1 # 消耗一次尝试机会

        if trigger_ip_refresh:
            if retries_done < MAX_RETRIES: # 确保还有尝试次数剩余
                run_warp_refresh(attempt_info) # 调用WARP刷新
            else:
                print(f"--- {attempt_info} 已达到最大尝试次数，即使需要IP刷新，也不再执行。---")
        
        if retries_done < MAX_RETRIES:
            print(f"等待 {RETRY_DELAY_SECONDS} 秒后进行下一次尝试 ({retries_done + 1}/{MAX_RETRIES})...")
            time.sleep(RETRY_DELAY_SECONDS)

# 如果循环结束仍未成功
if not netflix_check_successful:
    print(f"\n--- 脚本失败结束：已达到最大尝试次数 ({MAX_RETRIES})，仍无法确认页面无限制信息 ---")
    sys.exit(1) # 异常退出
