# MQSim GC Trigger Reproduction — Run Log & Results

PPT 가이드라인(§0~§10)을 그대로 따라 MQSim에서 GC를 강제 트리거하고,
출력 XML의 `GC_Read_TR_Queue` / `GC_Write_TR_Queue` / `GC_Erase_TR_Queue`,
FTL `Total_GC_Executions`로 트리거가 실제 발생했는지 검증한 기록.

---

## 0. 작업 디렉토리 구조

```
~/mqsim_gc_exp/MQSim/
├── MQSim                       # 빌드된 바이너리
├── ssdconfig.xml               # 원본 (수정 안 함)
├── workload.xml                # 원본 (수정 안 함)
├── exp_configs/
│   ├── ssd_baseline_occ50.xml  # baseline용 SSD config
│   └── ssd_target_occ95.xml    # target 용 SSD config
├── exp_workloads/
│   ├── wl_baseline_occ50.xml   # baseline 단일 IO_Scenario
│   └── wl_target_occ95.xml     # target 단일 IO_Scenario
├── run_baseline/               # 실행 디렉토리 (스코프 격리)
│   ├── MQSim, ssd.xml, wl.xml
│   └── wl_scenario_1.xml       # MQSim이 생성한 출력
├── run_target/
│   └── … 동일 구조
├── logs/{baseline,target}.log
└── results/
    ├── baseline_occ50_thr05.xml   # run_baseline/wl_scenario_1.xml 복사본
    ├── target_occ95_thr05.xml     # run_target/wl_scenario_1.xml 복사본
    └── SUMMARY.md                 # 이 파일
```

MQSim은 출력 XML을 **워크로드 파일과 동일한 디렉토리**에 `<workload>_scenario_<n>.xml`
형식으로 쓰기 때문에, 두 실험을 같은 폴더에서 병렬로 돌리면 파일이 충돌한다.
그래서 `run_baseline/`, `run_target/` 두 디렉토리를 분리해 각각 실행했다.

---

## 1. Clone & Build

```bash
mkdir -p ~/mqsim_gc_exp && cd ~/mqsim_gc_exp
git clone https://github.com/CMU-SAFARI/MQSim.git
cd MQSim
make clean && make
```

도구 버전 (서버 환경):
- `git 2.25.1`, `g++ 11.4.0` (Ubuntu 11.4.0-2ubuntu1~20.04), `GNU Make 4.2.1`
- Ubuntu 20.04 LTS / Linux 5.15

빌드는 단순 `make`로 통과 — 추가 패치/조정 없음.

---

## 2. ⚠️ 가이드 오타 수정 — `GC_Exec_Threshold`

가이드에는 `GC_Exect_Threshold` 라고 적혀 있지만, **현재 MQSim 코드/기본 XML의
실제 태그 이름은 `GC_Exec_Threshold`** 다. (README §23은 오타가 그대로 있고,
`ssdconfig.xml` 라인 33은 `GC_Exec_Threshold`로 올바르게 적혀 있다.)

가이드 문자열을 그대로 `grep`/XML 패치에 쓰면 0건 매칭되어 threshold 변경이
**조용히 실패**한다. 이 실험에서는 `GC_Exec_Threshold`를 사용했다.

```bash
grep -n "GC_Exec_Threshold" ssdconfig.xml   # 1 hit (line 33)
grep -n "GC_Exect_Threshold" ssdconfig.xml  # 0 hits
```

---

## 3. Workload 파일 단순화

원본 `workload.xml` 에는 IO_Scenario 가 3개(synthetic write-heavy 2 flow,
synthetic read-heavy 2 flow, trace-based) 들어 있고, 각 scenario 가 `wl_scenario_<n>.xml`
로 따로 출력된다. 분석 단순화를 위해 **첫 번째 scenario의 첫 번째 IO_Flow 1개만**
남긴 single-flow XML로 가공해서 사용했다.

가공 + 두 실험 config를 만든 Python 스크립트:

```python
# ~/mqsim_gc_exp/MQSim 에서 실행
import xml.etree.ElementTree as ET

# 1) 단일-flow 워크로드 빌더
src = ET.parse("workload.xml").getroot()
first_scenario = src.find("IO_Scenario")
flows = first_scenario.findall("IO_Flow_Parameter_Set_Synthetic")
for f in flows[1:]:
    first_scenario.remove(f)

def build(out, occ, ws, read_pct, qd, stop_time, addr_dist):
    root = ET.Element("MQSim_IO_Scenarios")
    sc = ET.SubElement(root, "IO_Scenario")
    flow = ET.fromstring(ET.tostring(flows[0]))
    sc.append(flow)
    def setv(tag, val):
        e = flow.find(tag)
        if e is not None: e.text = str(val)
    setv("Initial_Occupancy_Percentage", occ)
    setv("Working_Set_Percentage", ws)
    setv("Synthetic_Generator_Type", "QUEUE_DEPTH")
    setv("Read_Percentage", read_pct)
    setv("Address_Distribution", addr_dist)
    setv("Average_No_of_Reqs_in_Queue", qd)
    setv("Stop_Time", stop_time)
    setv("Total_Requests_To_Generate", 0)
    ET.ElementTree(root).write(out, encoding="us-ascii", xml_declaration=True)

build("exp_workloads/wl_baseline_occ50.xml", 50, 100, 1, 128, 100_000_000_000, "RANDOM_UNIFORM")
build("exp_workloads/wl_target_occ95.xml",   95,  10, 1, 128, 100_000_000_000, "RANDOM_UNIFORM")

# 2) SSD config 패치 (원본 복사 후 GC 관련 키 변경)
import shutil
shutil.copy("ssdconfig.xml", "exp_configs/ssd_baseline_occ50.xml")
shutil.copy("ssdconfig.xml", "exp_configs/ssd_target_occ95.xml")

def patch_ssd(path, thr):
    t = ET.parse(path); r = t.getroot()
    def setv(tag, val):
        for e in r.iter(tag): e.text = str(val)
    setv("Enabled_Preconditioning", "true")
    setv("GC_Exec_Threshold", thr)
    setv("GC_Block_Selection_Policy", "GREEDY")
    setv("Ideal_Mapping_Table", "true")
    setv("Preemptible_GC_Enabled", "false")
    t.write(path, encoding="us-ascii", xml_declaration=True)

patch_ssd("exp_configs/ssd_baseline_occ50.xml", 0.05)
patch_ssd("exp_configs/ssd_target_occ95.xml",   0.05)
```

`Stop_Time = 100,000,000,000 ns = 100 s` (시뮬레이션 시간).

---

## 4. 적용된 설정값

| 카테고리 | 파라미터 | Baseline | Target |
|---|---|---:|---:|
| SSD (공통) | `Enabled_Preconditioning` | true | true |
| | `Ideal_Mapping_Table` | true | true |
| | `Preemptible_GC_Enabled` | false | false |
| | `GC_Block_Selection_Policy` | GREEDY | GREEDY |
| | `GC_Exec_Threshold` | 0.05 | 0.05 |
| | `GC_Hard_Threshold` | 0.005 (원본 유지) | 0.005 |
| | `Overprovisioning_Ratio` | 0.07 (원본) | 0.07 |
| | HW: channels / chips / dies / planes | 8 / 4 / 2 / 2 (원본) | 동일 |
| | blocks/plane × pages/block × page | 2048 × 256 × 8 KB | 동일 |
| | NAND tech | MLC, Read 75 µs / Prog 750 µs / Erase 3.8 ms | 동일 |
| Workload | `Initial_Occupancy_Percentage` | **50** | **95** |
| | `Working_Set_Percentage` | **100** | **10** |
| | `Read_Percentage` | 1 | 1 |
| | `Address_Distribution` | RANDOM_UNIFORM | RANDOM_UNIFORM |
| | `Synthetic_Generator_Type` | QUEUE_DEPTH | QUEUE_DEPTH |
| | `Average_No_of_Reqs_in_Queue` (QD) | 128 | 128 |
| | `Stop_Time` (ns) | 100,000,000,000 | 100,000,000,000 |

베이스라인은 PPT의 “GC 미트리거” 기준선(50% occupancy, 0.05 임계치)이지만,
실제로는 99% write × random uniform × 100 s 라는 워크로드 강도 때문에
GC가 트리거된다(아래 결과 참조).

---

## 5. 실행 (병렬)

각각 별도 디렉토리에서 실행해 출력 XML 충돌을 피한다.

```bash
cd ~/mqsim_gc_exp/MQSim
mkdir -p run_baseline run_target logs results
cp MQSim run_baseline/ && cp MQSim run_target/
cp exp_configs/ssd_baseline_occ50.xml run_baseline/ssd.xml
cp exp_workloads/wl_baseline_occ50.xml run_baseline/wl.xml
cp exp_configs/ssd_target_occ95.xml   run_target/ssd.xml
cp exp_workloads/wl_target_occ95.xml  run_target/wl.xml

( cd run_baseline && ./MQSim -i ssd.xml -w wl.xml > ../logs/baseline.log 2>&1 ) &
BPID=$!
( cd run_target   && ./MQSim -i ssd.xml -w wl.xml > ../logs/target.log   2>&1 ) &
TPID=$!
wait $BPID && echo "baseline exit=$?"
wait $TPID && echo "target exit=$?"

cp run_baseline/wl_scenario_1.xml results/baseline_occ50_thr05.xml
cp run_target/wl_scenario_1.xml   results/target_occ95_thr05.xml
```

### 측정된 실행 시간 (real time)
- baseline: `Total simulation time: 0:3:51` (231 s, exit 0)
- target:   `Total simulation time: 0:8:31` (511 s, exit 0)

### 피크 메모리 (RSS)
- baseline ≈ 6.2 GB, target ≈ 4.8 GB (`ps -o rss`).

### Target 실행 시 출력된 경고
```
The specified initial occupancy value could not be satisfied as the
working set of workload #0 is small. MQSim made some adjustments!
```
의미: `Initial_Occupancy=95%`인데 `Working_Set=10%`이라 워크로드 LBA 범위가 너무 좁아
95%를 다 채울 수 없어 MQSim이 내부 보정함. 시뮬레이션은 정상 진행됨.

---

## 6. 출력 XML 구조 (검증할 때 본 것)

`results/<run>.xml` 안에서 우리가 확인한 핵심 노드들:

```
<MQSim_Results>
  …
  <SSDDevice.FTL Issued_Flash_Erase_CMD="…"
                 Issued_Flash_Multiplane_Erase_CMD="…"
                 Total_GC_Executions="…"
                 Average_Page_Movement_For_GC="…"
                 Total_WL_Executions="…" … />
  <SSDDevice.TSU.User_Read_TR_Queue.Priority.{HIGH|MEDIUM|LOW|URGENT}   …/>  # 32 × 4 = 128 노드
  <SSDDevice.TSU.User_Write_TR_Queue.Priority.…                        …/>  # 128 노드
  <SSDDevice.TSU.Mapping_Read_TR_Queue  …/>                                 # 32 노드
  <SSDDevice.TSU.Mapping_Write_TR_Queue …/>                                 # 32 노드
  <SSDDevice.TSU.GC_Read_TR_Queue   Name="GC_Read_TR_Queue@<ch>@<chip>"
                                    No_Of_Transactions_Enqueued="…"
                                    No_Of_Transactions_Dequeued="…"
                                    Max_Queue_Length="…"
                                    Avg_Queue_Length="…"
                                    Max_Transaction_Waiting_Time="…"
                                    Avg_Transaction_Waiting_Time="…" />   # 32 노드 (8ch × 4chip)
  <SSDDevice.TSU.GC_Write_TR_Queue  … />                                  # 32 노드
  <SSDDevice.TSU.GC_Erase_TR_Queue  … />                                  # 32 노드
  <Host.IO_Flow>
    <Name>Host.IO_Flow.Synth.No_0</Name>
    <Request_Count>…</Request_Count>
    <Read_Request_Count>…</Read_Request_Count>
    <Write_Request_Count>…</Write_Request_Count>
    <Device_Response_Time>…</Device_Response_Time>          # 평균, µs
    <Max_Device_Response_Time>…</Max_Device_Response_Time>  # tail
    …
  </Host.IO_Flow>
</MQSim_Results>
```

가이드 §7의 표시 이름(`NRequests`/`NDepartures`)은 `Queue_Probe::Snapshot`에서만
쓰이고, 실제 TSU XML은 `No_Of_Transactions_Enqueued`/`_Dequeued`로 저장된다.
검증 스크립트는 이 이름들을 본다.

검증용 한줄 `grep`:
```bash
grep -oE 'No_Of_Transactions_Enqueued="[0-9]+"' results/target_occ95_thr05.xml | head
```

집계 스크립트(Python):
```python
import xml.etree.ElementTree as ET
KINDS = ("User_Read_TR_Queue","User_Write_TR_Queue",
         "Mapping_Read_TR_Queue","Mapping_Write_TR_Queue",
         "GC_Read_TR_Queue","GC_Write_TR_Queue","GC_Erase_TR_Queue")
root = ET.parse("results/target_occ95_thr05.xml").getroot()
agg = {}
for e in root.iter():
    for k in KINDS:
        if k in e.tag and "No_Of_Transactions_Enqueued" in e.attrib:
            d = agg.setdefault(k, {"enq":0,"deq":0,"maxQ":0,"maxW":0})
            d["enq"] += int(e.attrib["No_Of_Transactions_Enqueued"])
            d["deq"] += int(e.attrib["No_Of_Transactions_Dequeued"])
            d["maxQ"] = max(d["maxQ"], int(e.attrib["Max_Queue_Length"]))
            d["maxW"] = max(d["maxW"], int(e.attrib["Max_Transaction_Waiting_Time"]))
            break
for k, v in agg.items(): print(k, v)
```

---

## 7. 결과 — Baseline vs Target

### 7.1 FTL statistics
| FTL 통계 | Baseline | Target |
|---|---:|---:|
| `Issued_Flash_Read_CMD` | 490,159 | 883,010 |
| `Issued_Flash_Program_CMD` | 2,584,094 | 1,120,529 |
| `Issued_Flash_Erase_CMD` | 9,476 | 4,021 |
| `Issued_Flash_Multiplane_Erase_CMD` | 345 | 386 |
| `Total_GC_Executions` | **10,039** | **4,666** |
| `Average_Page_Movement_For_GC` | **43.73** | **187.89** |
| `Total_WL_Executions` | 127 | 127 |

### 7.2 TSU TR queue 집계 (32 큐 = 8 ch × 4 chip 합산; User_*는 priority class 4종 × 32 = 128 큐)

| Queue | qcnt | Enq (Baseline) | Enq (Target) | Max Q len (B / T) | Avg wait µs (B / T) | Max wait µs (B / T) |
|---|---:|---:|---:|---:|---:|---:|
| User_Read | 128 | 21,998 | 3,296 | 5 / 5 | 1,206 / 16,685 | 775,092 / 2,767,135 |
| User_Write | 128 | 2,180,095 | 329,661 | 194 / 240 | 2,663 / 14,527 | 830,112 / 2,627,975 |
| Mapping_Read | 32 | 0 | 0 | — | — | — |
| Mapping_Write | 32 | 0 | 0 | — | — | — |
| **GC_Read** | 32 | **471,125** | **907,448** | 506 / 713 | 3,512 / 17,500 | 32,519 / 66,892 |
| **GC_Write** | 32 | **471,125** | **907,448** | 585 / **2,312** | 35,434 / **372,311** | 256,763 / 1,349,724 |
| **GC_Erase** | 32 | **10,166** | **4,793** | 6 / 16 | 64,176 / 775,305 | 594,312 / **2,621,405** |

Mapping_* 큐가 모두 0인 이유: `Ideal_Mapping_Table=true`로 CMT 미스가 없도록 설정.

### 7.3 Host IO_Flow

| | Baseline | Target |
|---|---:|---:|
| Request_Count | 2,202,508 | 333,264 |
| Read / Write requests | 21,998 / 2,180,510 | 3,296 / 329,968 |
| IOPS | 22,004 | 3,322 |
| Device_Response_Time (avg, µs) | 5,811 | **38,421** |
| Max_Device_Response_Time (µs) | 775,181 | **2,767,224** |
| End_to_End_Request_Delay (avg, µs) | 5,811 | 38,421 |

### 7.4 Derived

| | Baseline | Target |
|---|---:|---:|
| WAF = (user_w + gc_w) / user_w | 1.216 | **3.753** |
| GC_Write per host write | 0.216 | **2.750** |

---

## 8. Verdict — GC 트리거 검증 완료

GC_Read / GC_Write / GC_Erase 트랜잭션 카운트가 **두 실험 모두에서 non-zero**
→ 가이드 §7의 acceptance 조건 충족.

Target은 추가로 “고점유율 steady-state” 특성을 분명히 보여준다:
- 회당 valid page copy 4.3× 증가 (43.73 → 187.89)
- WAF 1.22 → 3.75 (3× 악화)
- IOPS 6.6× 폭락 (22 k → 3.3 k)
- 평균 device latency 6.6× 악화 (5.8 ms → 38.4 ms)
- GC_Write 큐 max length 4× 증가 (585 → 2,312)
- GC_Erase max wait 4.4× 증가 (0.59 s → 2.62 s)

PPT가 예측한 “high occupancy × 작은 working set × write-heavy random”
= GC가 IO 패스를 지배 → 지연/꼬리 지연 폭증, 의 정성적 변화가 그대로 재현됐다.

가이드 §8의 escalation(`occ=98 / ws=5 / thr=0.10`) **불필요**.

---

## 9. 흥미로운 부수 관측

1. **Baseline(occ=50)에서도 GC가 트리거됨.** PPT의 “50%에서는 GC 미트리거”는
   짧은 시뮬레이션(예: ~1 s) 또는 다른 워크로드 강도 가정이었을 가능성이 있다.
   `Stop_Time=100 s`, `QD=128`, `Read%=1`, `RANDOM_UNIFORM`이면 OP(7%)는 빠르게
   소진된다. baseline은 “GC가 거의 안 도는 조건”이 아니라 “GC가 가끔 도는 조건”이다.

2. **Target에서 `Total_GC_Executions`가 baseline보다 적다**(10,039 → 4,666). 모순이 아니다:
   target은 회당 valid page copy 양이 4.3배라 한 번의 GC가 훨씬 비싸고, GC가 user IO를
   심하게 막아 host IOPS 자체가 1/6로 떨어졌기 때문에 100 s 동안 처리한 요청 자체가 적다.

3. **Target Max_Device_Response_Time ≈ 2.77 s** — 단일 요청이 ~2.7초 대기.
   GC_Erase max wait(2.62 s)와 거의 같다. tail latency는 GC erase에 막혀서 발생함이
   수치적으로 확인된다.

---

## 10. 재현 절차 한 줄 요약

```bash
git clone https://github.com/CMU-SAFARI/MQSim.git && cd MQSim && make
# §3의 Python 스크립트로 exp_configs/, exp_workloads/ 생성
# §5 그대로 run_baseline / run_target 분리해서 ./MQSim -i ssd.xml -w wl.xml 병렬 실행
# results/<run>.xml 의 SSDDevice.TSU.GC_*_TR_Queue / SSDDevice.FTL@Total_GC_Executions 확인
```
