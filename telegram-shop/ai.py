"""ИИ-модуль магазина: генерация описаний, SEO-меты, рекламы, поиск аналогов в интернете.

Работает с любым OpenAI-совместимым API (OpenAI, DeepSeek, YandexGPT-через-прокси,
OpenRouter, локальные модели и т.п.) — настройки в админке (Настройки → ИИ):
  api_key, base_url, model.
Поиск аналогов: через Tavily API (ключ там же), иначе — ссылки на маркетплейсы
по сгенерированному запросу.
Без ключа модуль вежливо сообщает, что ИИ не настроен.
"""
import json
import logging
import re
import urllib.parse
from html import escape

import requests

log = logging.getLogger("shop.ai")

SYSTEM_PROMPT = (
    "Ты — профессиональный копирайтер и маркетолог интернет-магазина. "
    "Пиши на русском языке, продающе, конкретно, без воды и клише. "
    "Отвечай ТОЛЬКО валидным JSON без markdown-разметки."
)


def _cfg(store) -> dict:
    return (store.settings.get("ai") or {})


def available(store) -> bool:
    c = _cfg(store)
    return bool(c.get("enabled") and c.get("api_key"))


def _chat(store, messages: list, temperature: float = 0.7) -> str:
    c = _cfg(store)
    if not available(store):
        raise ValueError("ИИ не настроен: укажите API-ключ в админке (Настройки → ИИ)")
    body = {
        "model": c.get("model") or "gpt-4o-mini",
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
        "temperature": temperature,
    }
    r = requests.post((c.get("base_url") or "https://api.openai.com/v1").rstrip("/") + "/chat/completions",
                      json=body, headers={"Authorization": "Bearer " + c["api_key"]}, timeout=60)
    if r.status_code >= 400:
        log.warning("ИИ: %s %s", r.status_code, r.text[:300])
        raise ValueError("Ошибка ИИ-API: " + str(r.text[:200]))
    data = r.json()
    return data["choices"][0]["message"]["content"]


def _json_answer(store, user_prompt: str, temperature: float = 0.7) -> dict:
    text = _chat(store, [{"role": "user", "content": user_prompt}], temperature)
    text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
        raise ValueError("ИИ вернул некорректный ответ, попробуйте ещё раз")


def product_brief(p: dict, shop: str) -> str:
    return (f"Магазин: {shop}. Товар: {p['name']}. Категория: {p.get('category', '')}. "
            f"Цена: {p['price']} ₽. Старая цена: {p.get('old_price') or 'нет'}. "
            f"Исходное описание: {p.get('description') or 'нет'}.")


# ---------------------------------------------------------------- генерация
def generate_description(store, product: dict) -> dict:
    """SEO-описание, заголовок и meta description для карточки товара."""
    prompt = (
        f"{product_brief(product, store.settings['shop_name'])}\n\n"
        "Создай карточку товара и верни строгий JSON с полями:\n"
        "{\"title\": \"SEO-заголовок до 60 символов со словом купить\",\n"
        " \"meta\": \"meta description 120-155 символов с ценой и выгодой\",\n"
        " \"description\": \"продающее описание 250-400 символов: 1-й абзац выгоды, 2-й — характеристики/сценарии, 3-й — призыв\"}"
    )
    return _json_answer(store, prompt, 0.6)


def generate_ad_copy(store, product: dict) -> dict:
    """Рекламные материалы: пост для соцсетей, хештеги, слоган, сценарий ролика."""
    prompt = (
        f"{product_brief(product, store.settings['shop_name'])}\n\n"
        "Подготовь рекламу и верни строгий JSON с полями:\n"
        "{\"post\": \"пост для Telegram/VK 200-300 символов с эмодзи и призывом\",\n"
        " \"hashtags\": [\"5-8 хештегов\"],\n"
        " \"slogan\": \"короткий слоган для баннера до 6 слов\",\n"
        " \"video_script\": \"сценарий видеоролика 15 секунд: 3-4 сцены, для каждой — кадр и текст титра\"}"
    )
    return _json_answer(store, prompt, 0.8)


def generate_article(store, topic: str = "", product: dict = None) -> dict:
    """Статья для блога магазина (обзор товара или тема)."""
    if product:
        subject = (f"Товар: {product['name']}. Категория: {product.get('category', '')}. "
                   f"Цена: {product['price']} ₽. Описание: {product.get('description') or 'нет'}.")
        topic_hint = f"обзор товара «{product['name']}»: как выбрать, на что смотреть, кому подойдёт"
    else:
        subject = f"Тема: {topic}"
        topic_hint = topic
    prompt = (
        f"{subject}\nМагазин: {store.settings['shop_name']}.\n\n"
        f"Напиши статью для блога интернет-магазина на тему «{topic_hint}» и верни строгий JSON с полями:\n"
        '{"title": "заголовок до 70 символов с ключевыми словами",\n'
        ' "excerpt": "краткое описание статьи 120-160 символов для списка и meta description",\n'
        ' "content": "текст статьи 600-900 слов. Абзацы разделяй двойным переносом строки. '
        'Структура: введение с болью читателя, основная часть с конкретными советами/фактами, '
        'заключение с призывом. В конце добавь абзац про магазин и доставку",\n'
        ' "slug": "латиницей-через-дефис-краткий-slug"}'
    )
    return _json_answer(store, prompt, 0.75)


def generate_product_content(store, product: dict, mode: str) -> dict:
    """Генерация контента для складского приложения.
    mode: title | listing | telegram
    Работает с любым OpenAI-совместимым API. Бесплатные варианты (впишите в админку
    Настройки → ИИ): Groq (base_url https://api.groq.com/openai/v1, model llama-3.3-70b-versatile,
    ключ бесплатно на groq.com), Google Gemini (base_url
    https://generativelanguage.googleapis.com/v1beta/openai, бесплатный ключ в AI Studio),
    OpenRouter (бесплатные модели :free), DeepSeek (дёшево), GigaChat.
    """
    brief = product_brief(product, store.settings["shop_name"])
    prompts = {
        "title": (
            f"{brief}\nПридумай 3 варианта продающего названия товара для витрины "
            "(до 60 символов каждый, с ключевыми словами). Верни строгий JSON: "
            '{"titles": ["вариант 1", "вариант 2", "вариант 3"]}'),
        "listing": (
            f"{brief}\nНапиши текст объявления для продажи: первый абзац — выгода и состояние, "
            "второй — характеристики, третий — условия (доставка, оплата). 200-300 символов. "
            'Верни строгий JSON: {"text": "..."}'),
        "telegram": (
            f"{brief}\nПодготовь пост для Telegram-канала магазина: текст 200-300 символов "
            "с эмодзи и призывом к заказу, плюс 5-7 хештегов. Верни строгий JSON: "
            '{"text": "...", "hashtags": ["...", "..."]}'),
        "vk": (
            f"{brief}\nНапиши пост для сообщества ВКонтакте: до 2000 символов, "
            "заголовок с эмодзи, описание, цена, призыв перейти в каталог, 5-8 хештегов. "
            'Верни строгий JSON: {"text": "...", "hashtags": ["...", "..."]}'),
        "instagram": (
            f"{brief}\nНапиши пост для Instagram: короткий продающий текст до 800 символов "
            "с эмодзи, призывом написать в Direct, и 25-30 хештегов (общие + нишевые). "
            'Верни строгий JSON: {"text": "...", "hashtags": ["...", "..."]}'),
    }
    return _json_answer(store, prompts[mode], 0.7)


def find_similar(store, product: dict) -> dict:
    """Поиск аналогичных товаров в интернете: Tavily (если есть ключ) или ссылки на маркетплейсы."""
    brief = product_brief(product, store.settings["shop_name"])
    query_prompt = (
        f"{brief}\nВерни строгий JSON: {{\"query\": \"лучший поисковый запрос для поиска аналогов этого товара на маркетплейсах, до 8 слов\"}}"
    )
    q = _json_answer(store, query_prompt, 0.3).get("query") or product["name"]

    c = _cfg(store)
    tavily_key = (c.get("tavily_key") or "").strip()
    results = []
    if tavily_key:
        try:
            r = requests.post("https://api.tavily.com/search", json={
                "api_key": tavily_key, "query": q,
                "search_depth": "basic", "max_results": 6,
                "include_answer": True,
            }, timeout=30)
            r.raise_for_status()
            data = r.json()
            for res in data.get("results", [])[:6]:
                results.append({"title": res.get("title", ""), "url": res.get("url", ""),
                                "snippet": (res.get("content") or "")[:160]})
        except Exception as e:
            log.warning("Tavily: %s", e)

    links = []
    if not results:
        qq = urllib.parse.quote(q)
        links = [
            {"title": "Яндекс.Маркет", "url": f"https://market.yandex.ru/search?text={qq}"},
            {"title": "Ozon", "url": f"https://www.ozon.ru/search/?text={qq}"},
            {"title": "Wildberries", "url": f"https://www.wildberries.ru/catalog/0/search.aspx?search={qq}"},
            {"title": "AliExpress", "url": f"https://aliexpress.ru/wholesale?SearchText={qq}"},
        ]
    return {"query": q, "results": results, "market_links": links}
