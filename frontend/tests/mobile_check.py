"""모바일(iPhone 13, 390×844, 터치) 사용성 자동 점검.

사용법:
    pip install playwright && playwright install chromium
    python frontend/tests/mobile_check.py https://ai-assistant-frontend-virid.vercel.app

점검 항목
  1. 가로 스크롤 없음 (본문 폭 ≤ 화면 폭)
  2. 상단 탭(채팅/기록/데이터) 노출, 한 번에 패널 1개만 표시
  3. 탭 전환: 데이터 → 요약·그래프 표시 / 기록 → 대화 목록 표시 / 채팅 → 입력창 표시
  4. 그래프 터치 → 툴팁(날짜·값·7일 평균) 표시
  5. 기록 탭에서 대화를 탭하면 채팅 탭으로 돌아오며 메시지 재표시
  6. 입력창·전송 버튼 터치 영역 ≥ 36px
"""
import asyncio
import sys

from playwright.async_api import async_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5500/index.html"
results: list[tuple[bool, str]] = []


def check(ok: bool, label: str) -> None:
    results.append((bool(ok), label))
    print(("PASS " if ok else "FAIL ") + label)


async def visible_panels(page) -> list[str]:
    return await page.eval_on_selector_all(
        "[data-panel]", "els => els.filter(e => getComputedStyle(e).display !== 'none').map(e => e.dataset.panel)")


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(**({"executable_path": sys.argv[2]} if len(sys.argv) > 2 else {}))
        ctx = await browser.new_context(**p.devices["iPhone 13"])
        page = await ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(URL, wait_until="networkidle", timeout=90000)
        await page.wait_for_function("document.querySelector('#summaryGrid').children.length > 0", timeout=90000)

        sw, vw = await page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
        check(sw <= vw, f"가로 스크롤 없음 (scrollWidth {sw} ≤ viewport {vw})")
        check(await page.is_visible(".tabs"), "상단 탭 바 표시")
        panels = await visible_panels(page)
        check(panels == ["chat"], f"초기 화면은 채팅 패널만 표시 ({panels})")

        await page.tap('.tab[data-view="data"]')
        panels = await visible_panels(page)
        check(panels == ["data"], f"데이터 탭 → 데이터 패널만 표시 ({panels})")
        check(await page.is_visible("#summaryGrid") and await page.locator("#chart svg").count() == 1,
              "데이터 탭에 요약·추세 그래프 렌더링")

        box = await page.locator("#chart svg").bounding_box()
        await page.touchscreen.tap(box["x"] + box["width"] * 0.6, box["y"] + box["height"] / 2)
        tip = await page.locator("#chart .tip").text_content()
        check(bool(tip) and "7일" in tip, f"그래프 터치 → 툴팁 표시 ('{(tip or '').strip()}')")

        await page.tap('.tab[data-view="history"]')
        check(await visible_panels(page) == ["history"], "기록 탭 → 대화 목록 패널만 표시")
        items = await page.locator(".conv-item").count()
        if items:
            await page.locator(".conv-item .meta").first.tap()
            await page.wait_for_selector(".msg.user", timeout=30000)
            check(await visible_panels(page) == ["chat"] and await page.locator(".msg").count() >= 2,
                  f"대화 탭 → 채팅 탭으로 전환되며 메시지 {await page.locator('.msg').count()}개 재표시")
        else:
            check(False, "저장된 대화가 없어 불러오기 흐름을 확인하지 못함")

        await page.tap('.tab[data-view="chat"]')
        ib = await page.locator("#chatInput").bounding_box()
        sb = await page.locator("#sendBtn").bounding_box()
        check(ib["height"] >= 36 and sb["height"] >= 36,
              f"입력창·전송 버튼 터치 영역 (입력 {ib['height']:.0f}px, 전송 {sb['height']:.0f}px ≥ 36px)")
        check(not errors, f"자바스크립트 오류 없음 ({errors[:1]})")
        await browser.close()

    passed = sum(ok for ok, _ in results)
    print(f"\n결과: {passed}/{len(results)} 통과 — {URL}")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    asyncio.run(main())
