import asyncio
import re
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from playwright.async_api import async_playwright


app = FastAPI(title="D&D Beyond Sheet Proxy")

_pw = None
_browser = None
_lock = asyncio.Lock()


@app.on_event("startup")
async def startup_event():
    global _pw, _browser
    _pw = await async_playwright().start()
    _browser = await _pw.chromium.launch(headless=True)


@app.on_event("shutdown")
async def shutdown_event():
    global _pw, _browser
    try:
        if _browser:
            await _browser.close()
    finally:
        _browser = None
        if _pw:
            await _pw.stop()
            _pw = None


async def _get_element_text(page, selector: str, timeout: int = 10000) -> str:
    locator = page.locator(selector).first
    await locator.wait_for(timeout=timeout)
    return (await locator.inner_text()).strip()


async def _has_proficiency_indicator(element) -> bool:
    try:
        sel = ", ".join([
            ".ct-proficiency-bubble svg circle",
            ".ct-proficiency-bubble__icon svg circle",
            ".ddbc-proficiency-bubble svg circle",
            "svg.ct-proficiency-bubble__svg circle",
            "svg circle",
        ])
        circles = element.locator(sel)
        count = await circles.count()
        if count == 0:
            return False
        for idx in range(min(count, 5)):
            c = circles.nth(idx)
            r = await c.get_attribute("r")
            fill = await c.get_attribute("fill")
            if (r and r != "0") or (fill and fill.lower() != "none"):
                return True
        return True
    except Exception:
        return False


async def _get_abilities(page) -> list[str]:
    locator = page.locator(".ddbc-ability-summary")
    await locator.first.wait_for(timeout=10000)
    raw_texts = await locator.all_inner_texts()
    abbrev_map = {
        "STRENGTH": "STR",
        "DEXTERITY": "DEX",
        "CONSTITUTION": "CON",
        "INTELLIGENCE": "INT",
        "WISDOM": "WIS",
        "CHARISMA": "CHA",
    }
    abilities = []
    for text in raw_texts:
        parts = [p.strip() for p in text.splitlines() if p.strip()]
        if len(parts) >= 4:
            full_name = parts[0].upper()
            abbrev = abbrev_map.get(full_name, parts[0][:3].upper())
            abilities.append(f"{abbrev} {parts[1]}{parts[2]} ({parts[3]})")
        else:
            abilities.append(" ".join(parts))
    return abilities


async def _get_avatar(page) -> str:
    portrait = page.locator(".ddbc-character-avatar__portrait").first
    await portrait.wait_for(timeout=10000)
    if src := await portrait.get_attribute("src"):
        return src.strip()
    try:
        img = page.locator(".ddbc-character-avatar__portrait img").first
        await img.wait_for(timeout=3000)
        if src := await img.get_attribute("src"):
            return src.strip()
    except Exception:
        pass
    if style := await portrait.get_attribute("style"):
        match = re.search(r"background-image:\s*url\(['\"]?(.*?)['\"]?\)", style)
        if match:
            return match.group(1)
    return ""


async def _get_saving_throws(page) -> list[str]:
    abilities = ["str", "dex", "con", "int", "wis", "cha"]
    abbrevs = ["STR", "DEX", "CON", "INT", "WIS", "CHA"]
    await page.locator(".ddbc-saving-throws-summary__ability--str").first.wait_for(timeout=10000, state="attached")
    saves: list[str] = []
    for i, suffix in enumerate(abilities):
        try:
            ability_elem = page.locator(f".ddbc-saving-throws-summary__ability--{suffix}").first
            text = await ability_elem.inner_text()
            parts = [p.strip() for p in text.splitlines() if p.strip()]
            modifier = f"{parts[-2]}{parts[-1]}" if len(parts) >= 2 else "+0"
            is_proficient = await _has_proficiency_indicator(ability_elem)
            save_text = f"{abbrevs[i]} {modifier}"
            if is_proficient:
                save_text = f"**{save_text}**"
            saves.append(save_text)
        except Exception:
            saves.append(f"{abbrevs[i]} +0")
    return saves


async def _get_skills(page) -> list[str]:
    await page.locator(".ct-skills__item").first.wait_for(timeout=10000)
    skill_items = page.locator(".ct-skills__item")
    count = await skill_items.count()
    skills: list[str] = []
    for i in range(count):
        item = skill_items.nth(i)
        text = await item.inner_text()
        parts = [p.strip() for p in text.splitlines() if p.strip()]
        if len(parts) >= 4:
            skill_name = parts[1]
            bonus = f"{parts[2]}{parts[3]}"
            is_proficient = await _has_proficiency_indicator(item)
            skill_text = f"{skill_name} {bonus}"
            if is_proficient:
                skill_text = f"**{skill_text}**"
            skills.append(skill_text)
    return skills


async def scrape_character(character_id: str) -> Optional[dict]:
    url = f"https://www.dndbeyond.com/characters/{character_id}"
    async with _lock:
        context = await _browser.new_context()
        page = await context.new_page()
    try:
        await page.goto(url, wait_until="networkidle")
        await page.wait_for_timeout(1000)
        title = await page.title()
        name_match = re.search(r"^(.+?)'s Character Sheet", title)
        name = name_match.group(1) if name_match else ""

        level_task = asyncio.create_task(_get_element_text(page, ".ddbc-character-progression-summary__level"))
        race_task = asyncio.create_task(_get_element_text(page, ".ddbc-character-summary__race"))
        classes_text_task = asyncio.create_task(_get_element_text(page, ".ddbc-character-summary__classes"))
        max_hp_task = asyncio.create_task(_get_element_text(page, "[data-testid='max-hp']"))
        ac_task = asyncio.create_task(_get_element_text(page, ".ddbc-armor-class-box__value"))
        speed_text_task = asyncio.create_task(_get_element_text(page, ".ct-quick-info__box--speed"))

        abilities_task = asyncio.create_task(_get_abilities(page))
        avatar_task = asyncio.create_task(_get_avatar(page))
        saves_task = asyncio.create_task(_get_saving_throws(page))
        skills_task = asyncio.create_task(_get_skills(page))

        level, race, classes_text, max_hp, ac, speed_text = await asyncio.gather(
            level_task, race_task, classes_text_task, max_hp_task, ac_task, speed_text_task
        )

        speed_match = re.search(r"(\d+)\s*ft", speed_text)
        speed = f"{speed_match.group(1)} ft." if speed_match else ""

        # Format classes
        class_pairs = re.findall(r"([A-Za-z][A-Za-z'\-\s]+?)\s+(\d{1,2})", classes_text or "")
        if not class_pairs:
            classes = (classes_text or "").strip()
        elif len(class_pairs) == 1:
            classes = class_pairs[0][0].strip()
        else:
            classes = " / ".join(f"{n.strip()} ({l})" for n, l in class_pairs)

        abilities, avatar, saves, skills = await asyncio.gather(
            abilities_task, avatar_task, saves_task, skills_task
        )
        avatar = (avatar or "").split("?")[0]

        return {
            "name": name,
            "level": level,
            "race": race,
            "classes": classes,
            "max_hp": max_hp,
            "ac": ac,
            "speed": speed,
            "abilities": abilities,
            "avatar": avatar,
            "saving_throws": saves,
            "skills": skills,
        }
    finally:
        await context.close()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/sheet/{character_id}")
async def get_sheet(character_id: str):
    try:
        data = await scrape_character(character_id)
        if not data:
            raise HTTPException(status_code=502, detail="Failed to scrape character")
        return JSONResponse(data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Run with: uvicorn tools.sheet_proxy:app --host 0.0.0.0 --port 8000