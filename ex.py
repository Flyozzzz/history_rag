"""
Быстрый end-to-end тест для сервиса истории.

Запуск как скрипта:
    python test_history_api.py

Запуск как pytest:
    pytest -q

Требуется: pip install httpx pytest pytest-asyncio
"""

import asyncio
import json
import os
import uuid

import httpx

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")


async def _happy_path(client: httpx.AsyncClient, user_id: str):
    messages = [
        {"role": "user", "content": "Привет, ассистент!", "type": "text"},
        {"role": "assistant", "content": "Здравствуйте! Чем могу помочь сегодня?", "type": "text"},

        # small-talk & preferences
        {"role": "user", "content": "Какой сегодня день недели?", "type": "text"},
        {"role": "assistant", "content": "Сегодня пятница — отличное время планировать выходные!", "type": "text"},

        {"role": "user", "content": "Посоветуй фильм для семейного вечера.", "type": "text"},
        {"role": "assistant", "content": "Рекомендую «Коко» — тепло, музыкально и подходит детям.", "type": "text"},

        # weather
        {"role": "user", "content": "Какая будет погода завтра?", "type": "text"},
        {"role": "assistant", "content": "По прогнозу +23 °C, без осадков; ветер слабый западный.", "type": "text"},

        # shopping
        {"role": "user", "content": "Найди, пожалуйста, кроссовки 42 размера до 80 €.", "type": "text"},
        {"role": "assistant", "content": "Нашёл Adidas RunFalcon 2.0 — 74 €. Добавить в корзину?", "type": "text"},

        {"role": "user", "content": "Да, добавь и оформи доставку на завтра.", "type": "text"},
        {"role": "assistant", "content": "Готово: доставка курьером к 18:00 завтрашнего дня.", "type": "text"},

        # hobbies
        {"role": "user", "content": "Напомни, что я люблю играть в настольный теннис.", "type": "text"},
        {"role": "assistant", "content": "Запомнила: настольный теннис — ваше хобби.", "type": "text"},

        # travel
        {"role": "user", "content": "Какие достопримечательности есть в Праге?", "type": "text"},
        {"role": "assistant", "content": "Карлов мост, Пражский Град и Староместская площадь.", "type": "text"},

        # follow-up
        {"role": "user", "content": "Сколько стоит вход в собор Святого Вита?", "type": "text"},
        {"role": "assistant", "content": "Полный билет — 350 CZK (≈14 €), детский — 200 CZK.", "type": "text"},

        # emotions
        {"role": "user", "content": "Я сегодня устал и немного расстроен.", "type": "text"},
        {"role": "assistant", "content": "Сочувствую. Может, сделать паузу и пройтись на свежем воздухе?",
         "type": "text"},

        # cooking
        {"role": "user", "content": "Дай быстрый рецепт пасты карбонара.", "type": "text"},
        {"role": "assistant", "content": "Спагетти, яйца, пармезан и гуанчале: 8 мин варки + 2 мин соус.",
         "type": "text"},

        # dates & reminders
        {"role": "user", "content": "Завтра дедлайн по отчёту, не дай забыть!", "type": "text"},
        {"role": "assistant", "content": "Поставила напоминание на 9:00: «Сдать отчёт».", "type": "text"},

        # music
        {"role": "user", "content": "Включи расслабляющую плейлист-джаз.", "type": "text"},
        {"role": "assistant", "content": "Запускаю плейлист «Jazz Chill» в Spotify.", "type": "text"},

        # learning
        {"role": "user", "content": "Как быстро выучить 20 английских слов?", "type": "text"},
        {"role": "assistant", "content": "Используйте метод «5-5-5»: 5 слов — 5 повторов — 5 контекстов.",
         "type": "text"},

        # sports score
        {"role": "user", "content": "Кто выиграл вчерашний матч Реал-Барса?", "type": "text"},
        {"role": "assistant", "content": "Барселона победила 2:1, голы — Левандовски и Фати.", "type": "text"},

        # personal data
        {"role": "user", "content": "Запомни: моё имя Денис.", "type": "text"},
        {"role": "assistant", "content": "Приятно познакомиться, Денис!", "type": "text"},

        # follow-up question using memory
        {"role": "assistant", "content": "Денис, хотите узнать прогноз на выходные для тенниса?", "type": "text"},
        {"role": "user", "content": "Да, пожалуйста!", "type": "text"},

        # ending
        {"role": "assistant", "content": "Суббота +25 °C, без ветра — идеальные условия для игры!", "type": "text"},
        {"role": "user", "content": "Спасибо, ты лучший!", "type": "text"},
        {"role": "assistant", "content": "Рада помочь 😊", "type": "text"}
    ]

    resp = await client.post("/add", json={"uuid": user_id, "messages": messages})
    resp.raise_for_status()
    assert resp.json()["stream_ids"], "Сервер не вернул id сообщений"

    # 2) читаем историю
    resp = await client.get("/history", params={"uuid": user_id, "limit": 10})
    resp.raise_for_status()
    history = resp.json()["messages"]

"""
    # 3) запрашиваем summary
    resp = await client.post("/summary", params={"uuid": user_id})
    resp.raise_for_status()
    summary = resp.json()["summary"]
    print("Summary:", summary)
    assert summary, "Пустая суммаризация"
"""

async def main():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        await _happy_path(client, str(12333))


if __name__ == "__main__":
    asyncio.run(main())

