# Passive SAE J1939 / ISOBUS acquisition on a Raspberry Pi

Source code, field recordings and benchmark data for the master's dissertation
*"Equivalência funcional de um sistema embarcado de código aberto para captura passiva e
decodificação determinística de redes SAE J1939/ISOBUS em maquinário agrícola"*
(Victor Augusto Bertin Borges, PPGTCA – Universidade Tecnológica Federal do Paraná, 2026)
and the derived journal article *"Evaluation of a passive SAE J1939 acquisition platform using a
commercial reference"*.

> **Resumo em português** no final deste arquivo.

---

## Repository layout

| Path | Content |
|---|---|
| [`acquisition/`](acquisition/) | Application that ran on the Raspberry Pi 5 during the tractor field test (18 April 2026). |
| [`software_metrics/`](software_metrics/) | Instrumented variant of the same application, used for the laboratory replay benchmark (CPU, RAM, queue and decoding-time sampling). |
| [`data/raw/`](data/raw/) | Raw CAN recordings: tractor test (prototype and commercial reference) and the Kuhn Accura traffic used for bench replay. |
| [`data/processed/`](data/processed/) | Decoded export of the tractor test and derived comparison files. |
| [`data/bench/`](data/bench/) | Input, raw/decoded output and performance samples of the laboratory replay benchmark. |
| [`data/dicionario/`](data/dicionario/) | PGN/SPN conversion table used by the decoder. |

---

## 1. `acquisition/` – field-test application

Entry point: `acquisition/main.py`. The decoder reads its conversion table from
`acquisition/src/dados/pgn_config.csv`.

### Architecture (as implemented)

1. `src/hardware.py` configures the SocketCAN interface with `ip link`. With the **"Modo Silencioso"**
   switch enabled (the default in the UI), the controller is set to `listen-only on`, and
   transmission from the application is blocked.
2. A **reader thread** (`MainSystem._thread_can_reader`) runs `candump <channel>` as a subprocess and
   reads its standard output line by line. For each frame it:
   - assigns the timestamp with `datetime.now()` (system wall clock, at the moment the Python
     process reads the line; truncated to milliseconds). The kernel/hardware timestamps of `candump`
     are **not** used;
   - writes the frame to `logs/raw_<session>.csv`;
   - decodes it (`src/j1939_core.py`) and writes each decoded parameter to `logs/decoded_<session>.csv`;
   - places each decoded parameter in a FIFO queue (`queue.Queue(maxsize=5000)`) for the UI.
3. The **UI thread** (Tk main loop, `customtkinter`) drains the queue every 50 ms and redraws
   text panels only every 15th item (visual sub-sampling).

Because both CSV files are written **before** the queue, a full queue affects only the display.
When the queue is full the incoming item is discarded from the display (*drop-newest*) and counted
as `Drops UI`; the recorded files are not affected.

### Provenance of `acquisition/main.py` (please read)

The bounded queue (`maxsize=5000`) and the `queue.Full` handling (drop-newest, `stat_dropped_ui_messages`)
were edited directly on the Raspberry Pi before the field test. The edited file on the Pi was not
preserved. On 13 November 2026 the author re-applied those same edits to the local copy of
`main.py` included here, and states that its content is equivalent to the version that ran in the
field. This file is therefore a **reconstruction**, not a byte-for-byte copy of the deployed file.
All other files in `acquisition/` are unchanged since April 2026.

### Other files

- `src/can_injector.py` – bench tool, runs on a **Windows PC** (pyserial, `COM10`). Replays a
  `candump` log through an Arduino + MCP2515 node, preserving the original inter-frame intervals.
  The Arduino firmware is not included in this repository.
- `src/gerador_config.py` – interactive helper that builds `ui_config.json` (gauges/LEDs shown on screen)
  from `pgn_config.csv`.
- `src/pgn_config.csv` – copy of `src/dados/pgn_config.csv` used by `gerador_config.py`.

---

## 2. `software_metrics/` – laboratory benchmark variant

Same application with the following differences relative to `acquisition/`:

- an extra thread (`_thread_metrics_logger`, uses `psutil`) appends one line **per second** to
  `src/dados/metricas_artigo.csv` with: CPU %, used RAM (MB), current UI-queue length,
  decoding time of the **most recent** frame (ms), cumulative received frames, and cumulative frames
  without a decoding result;
- the UI queue is **unbounded** (`queue.Queue()`). The 5000-item limit was introduced after this
  benchmark;
- minor UI layout differences (`app_window.py`, `gauges.py`, `status_leds.py`, `ui_config.json`).

The output of the benchmark session is in [`data/bench/`](data/bench/).

---

## 3. Data

### `data/raw/`

| File | Description |
|---|---|
| `tracktor_john_deere_log.csv` | Prototype raw log of the tractor test (John Deere 7230J, stationary, engine running, 250 kbit/s). Original file name on the Pi: `raw_2026-04-08_02-55-01.csv`. 19,957 frames. |
| `pcan_john_deere_log.trc` | Commercial reference recorded in parallel: **PEAK-System PCAN-USB Pro FD** (IPEH-004061), classic CAN, 250 kbit/s, **PCAN-View v6.0.0.1040**. Header start time: 18/04/2026 16:24:37 (local time). |
| `kuhn_accura_log.csv` | Kuhn Accura fertilizer-spreader traffic (`candump` format, `;`-separated). Same frames as `data/bench/kuhn_accura_replay_input.txt`. |

**Clock note.** The Raspberry Pi had no network time and no RTC battery in the field, so the dates
and times generated by the Pi (file names and timestamps) do not correspond to the real date. The
tractor test took place on **18 April 2026** (PCAN-View trace header); the Pi named the session
`2026-04-08_02-55-01`. Prototype timestamps are valid only as relative times within a recording.

### `data/processed/`

| File | Description |
|---|---|
| `decoded.csv` | Decoded export of the tractor test. Identical to the Pi's `decoded_2026-04-08_02-55-01.csv` except that the field separator was changed from `,` to `;`. 81,639 records. |
| `comparacao_deltat.csv` | Derived inter-frame-interval comparison (prototype vs. reference). |
| `categorizados.xlsx` | Classification of the decoded records used in the dissertation. |

### `data/bench/` – laboratory replay benchmark (6 April 2026, Pi clock)

| File | Description |
|---|---|
| `kuhn_accura_replay_input.txt` | Input replayed by `can_injector.py` (37,606 frames, `candump -l` format). |
| `raw_2026-04-06_17-04-28.csv` | Frames received by the Pi during the benchmark (34,536 frames). |
| `decoded_2026-04-06_17-04-28.csv` | Corresponding decoded export. |
| `metricas_artigo.csv` | 117 one-second samples written by `software_metrics/` (see Section 2). The decoding-time statistics reported in the dissertation (Table 1) were computed from the `Tempo_Decod_ms` column of this file, i.e. one sample of the most recent frame's decoding time per second. |

### `data/dicionario/`

`pgn_config.csv` – PGN/SPN definitions (start bit, length, scale, offset, unit) derived from the
SAE J1939 Digital Annex (J1939DA, May 2023). The J1939DA itself is a copyrighted SAE publication and must
be obtained from SAE International.

---

## 4. Runtime environment (field test)

| Item | Value |
|---|---|
| Computer | Raspberry Pi 5 |
| OS | Raspberry Pi OS 64-bit (Debian 13 "trixie"), Linux kernel 6.12 |
| Python | 3.13 (bytecode cache `cpython-313`) |
| CAN interface | MKS CANable Pro 2.0, firmware candleLight_fw `d13b6db` (gs_usb driver, SocketCAN) |
| Frame reception | `candump` (can-utils) |
| Python packages | see [`acquisition/requirements.txt`](acquisition/requirements.txt) |

`python-can` was installed on the Pi but is not imported by this code; reception uses `candump`.

### Running

```bash
sudo apt install can-utils python3-tk
pip install -r acquisition/requirements.txt
cd acquisition
python3 main.py
```

`sudo` rights are required because the application calls `ip link` and `candump` with `sudo`.
Logs are written to `acquisition/logs/`.

---

## 5. Archived versions

- Release used in the article: tag `v1.0.0` of this repository, archived on Zenodo
  (DOI: *to be added after release*).
- Dissertation-submission archive: https://doi.org/10.5281/zenodo.20532086

## 6. License

*To be defined by the authors before release `v1.0.0`.*

## 7. How to cite

Borges, V. A. B. *Equivalência funcional de um sistema embarcado de código aberto para captura passiva e
decodificação determinística de redes SAE J1939/ISOBUS em maquinário agrícola*. Dissertação de mestrado,
UTFPR, 2026.

---

## Resumo em português

Este repositório contém:

- **`acquisition/`**: o programa que rodou na Raspberry Pi 5 no ensaio do trator (18/04/2026). O `main.py` foi
  **reconstruído** em 13/11/2026: a limitação da fila (5000) e o descarte foram editados diretamente na Pi, e
  essas mesmas alterações foram reaplicadas na cópia local. Os demais arquivos estão inalterados desde abril de 2026.
- **`software_metrics/`**: a versão instrumentada usada no ensaio de bancada (métricas de CPU, RAM, fila e tempo
  de decodificação, amostradas a cada 1 s). Nessa versão a fila ainda não tinha limite.
- **`data/`**: os logs brutos do ensaio de campo (protótipo e PEAK PCAN-USB Pro FD / PCAN-View v6.0.0.1040),
  os arquivos decodificados e os dados do ensaio de bancada.

O relógio da Raspberry Pi não estava sincronizado em campo, então as datas nos nomes dos arquivos gerados pela
Pi não correspondem à data real do ensaio (18/04/2026).
