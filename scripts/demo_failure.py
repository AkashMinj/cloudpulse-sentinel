"""
Controlled failure scenario — injects real load to trigger detection.
"""
import time, requests, os, subprocess, sys
API = os.getenv("CLOUDPULSE_API_URL","http://localhost:8000")

def stress():
    # Actually burn CPU for ~30s to push metrics above 80% threshold
    p = subprocess.Popen([sys.executable,"-c",
        "import time\nend=time.time()+30\nwhile time.time()<end:\n x=0\n for _ in range(5_000_000): x+=1"])
    return p

def main():
    print("=== DEMO START ===")
    p = stress()
    for i in range(3):
        time.sleep(10)
        try:
            r = requests.post(f"{API}/api/v1/metrics/collect",timeout=20)
            print(f"  collect: {r.status_code}")
        except Exception as e:
            print(f"  collect error: {e}")
    p.wait()
    # Fetch open incident
    try:
        inc = requests.get(f"{API}/api/v1/incidents",params={"status":"open","limit":5},timeout=10).json()
        if inc.get("incidents"):
            print(f"  Incident detected: {inc['incidents'][0]['incident_type']}")
    except Exception as e:
        print(f"  fetch incident error: {e}")
    print("=== DEMO END ===")

if __name__=="__main__": main()
