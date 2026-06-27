"""Concurrency bench for eai-flow-ocr (Phase 2 T1).

Finds the single-container concurrency ceiling to decide the worker model
(asyncio.Semaphore vs arq queue). Sends N concurrent /ocr requests against a
small synthetic table PDF, reports success/latency/throughput per level.

Run inside the gateway container (has httpx + network to eai-flow-ocr):
  cd /app/backend && uv run python /app/mcp-server/ocr-service/bench_ocr.py

Watch container memory in another terminal:  docker stats eai-flow-ocr
"""

import asyncio
import io
import time

import httpx
from PIL import Image, ImageDraw

URL = "http://eai-flow-ocr:8010/ocr"


def make_pdf() -> bytes:
    img = Image.new("RGB", (1400, 900), "white")
    d = ImageDraw.Draw(img)
    xs = [80, 420, 760, 1100, 1320]
    ys = [80, 150, 220, 290, 360, 430, 500]
    for x in xs:
        d.line([(x, 80), (x, 500)], fill="black", width=3)
    for y in ys:
        d.line([(80, y), (1320, y)], fill="black", width=3)
    data = [
        ("序号", "项目名称", "单位", "含税单价", "合价"),
        ("1", "平整场地", "m2", "1.31", "1078.83"),
        ("2", "基础开挖", "m3", "7.63", "3785.93"),
        ("3", "回填方", "m3", "9.81", "3983.74"),
        ("4", "多孔砖墙", "m3", "556.99", "117446.91"),
    ]
    for i, row in enumerate(data):
        y = 110 + i * 70
        for j, v in enumerate(row):
            d.text((xs[j] + 20, y), v, fill="black")
    buf = io.BytesIO()
    img.save(buf, "PDF", resolution=150.0)
    return buf.getvalue()


async def one(client: httpx.AsyncClient, pdf: bytes):
    t = time.monotonic()
    try:
        r = await client.post(URL, files={"file": ("t.pdf", pdf, "application/pdf")})
        return time.monotonic() - t, r.status_code
    except Exception as exc:
        return time.monotonic() - t, repr(exc)[:60]


async def bench(level: int, pdf: bytes):
    async with httpx.AsyncClient(timeout=300) as client:
        t0 = time.monotonic()
        res = await asyncio.gather(*[one(client, pdf) for _ in range(level)])
        dur = time.monotonic() - t0
    ok = sum(1 for _, s in res if s == 200)
    lat = sorted(l for l, _ in res if isinstance(l, (int, float)))
    p50 = lat[len(lat) // 2] if lat else 0
    p99 = lat[-1] if lat else 0
    errs = [s for _, s in res if s != 200]
    print(
        f"N={level:>2}: ok={ok}/{level}  total={dur:5.1f}s  "
        f"p50={p50:4.1f}s  p99={p99:4.1f}s  "
        f"throughput={ok/dur:.2f} req/s"
        + (f"  ERRS={errs[:3]}" if errs else "")
    )
    return ok == level


async def main():
    pdf = make_pdf()
    print(f"=== eai-flow-ocr 并发压测(合成小PDF,{len(pdf)} bytes)===")
    for n in [1, 2, 4, 8]:
        ok = await bench(n, pdf)
        if not ok:
            print(f"  ⚠ N={n} 有失败,停止加压(可能到瓶颈)")
            break
        await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
