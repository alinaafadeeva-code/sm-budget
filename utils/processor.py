import pandas as pd
import re
from datetime import datetime
from .mappings import (
    STUDIO_CODES, STUDIO_ALIASES, ENTITY_STUDIOS, STUDIO_ENTITY,
    GENERAL_ENTITY, GENERAL_NETWORK, OCCUPANCY_STUDIOS,
)


def parse_amount(val) -> float:
    """Парсит сумму в российском формате: '7 074,00' → 7074.0"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return 0.0
    s = str(val).replace('\xa0', '').replace(' ', '').replace(',', '.')
    s = re.sub(r'[^\d.]', '', s)
    try:
        return float(s)
    except ValueError:
        return 0.0


def normalize_studio(raw: str) -> str:
    """
    Приводит комментарий к стандартному коду студии.
    Возвращает:
      - код студии (ПК1, ЧП, …)
      - 'ОБЩ'       — делить по юрлицу
      - 'ОБЩ СЕТЬ'  — делить по всей сети
      - ''           — пустое → будет трактоваться как ОБЩ
    """
    if not raw or str(raw).strip().lower() in ('nan', ''):
        return ''
    upper = str(raw).strip().upper()
    if upper == GENERAL_NETWORK.upper():
        return GENERAL_NETWORK
    if upper == GENERAL_ENTITY.upper():
        return GENERAL_ENTITY
    if upper in STUDIO_CODES:
        return upper
    if upper in STUDIO_ALIASES:
        return STUDIO_ALIASES[upper]
    # Попробуем найти совпадение внутри строки
    for alias, code in STUDIO_ALIASES.items():
        if alias in upper:
            return code
    for code in STUDIO_CODES:
        if code in upper:
            return code
    return upper  # вернём как есть, разберёмся в логах


def detect_entity(filename: str):
    """Определяет юрлицо по имени файла."""
    u = filename.upper()
    if 'ИПМ' in u or 'МУСТАФАЕВА' in u:
        return 'ИПМ'
    if 'ИПК' in u or 'КОНДРАТЮК' in u:
        return 'ИПК'
    if 'СМГ' in u or 'СМ ГРУПП' in u or 'СМГРУПП' in u or 'СМГРУПП' in u:
        return 'СМГ'
    if 'СМЛ' in u or 'ЛАЙВ' in u or 'LIVE' in u or 'СМ ЛАЙВ' in u:
        return 'СМЛ'
    return None


def process_registry(file_obj, entity: str) -> list[dict]:
    """
    Читает Excel-реестр и возвращает список транзакций.
    Каждая транзакция: {date, year, month, entity, studio, category_code, amount, description}
    studio может быть: код студии | 'ОБЩ' | 'ОБЩ СЕТЬ' | '' (трактуем как ОБЩ)
    """
    df = pd.read_excel(file_obj, header=None, dtype=str)
    transactions = []

    for _, row in df.iterrows():
        val0 = str(row.iloc[0]).strip()

        # Пропускаем строки-заголовки и итоги
        if val0.lower() in ('nan', '', '№ п/п', 'итого', '№'):
            continue

        # Строка с данными — первая колонка должна быть числом (порядковый номер)
        try:
            int(float(val0))
        except (ValueError, TypeError):
            continue

        # Дата
        date_raw = row.iloc[1]
        try:
            date = pd.to_datetime(date_raw)
        except Exception:
            continue

        # Сумма (колонка 4)
        amount = parse_amount(row.iloc[4])
        if amount <= 0:
            continue

        # Комментарий / студия (колонка 11)
        comment_raw = str(row.iloc[11]).strip() if len(row) > 11 else ''
        studio = normalize_studio(comment_raw)

        # Статья (последняя значимая колонка — 12)
        cat_raw = row.iloc[12] if len(row) > 12 else None
        try:
            category_code = int(float(str(cat_raw)))
        except (ValueError, TypeError):
            category_code = None

        # Описание (назначение платежа — колонка 6)
        description = str(row.iloc[6]).strip() if len(row) > 6 else ''
        if description.lower() == 'nan':
            description = ''

        transactions.append({
            'date':          date.strftime('%Y-%m-%d'),
            'year':          int(date.year),
            'month':         int(date.month),
            'entity':        entity,
            'studio':        studio,
            'category_code': category_code,
            'amount':        round(amount, 2),
            'description':   description,
            'type':          'expense',
        })

    return transactions


def apply_occupancy(transactions: list[dict], occupancy: dict) -> list[dict]:
    """
    Разносит «общие» транзакции по студиям согласно коэффициенту заполняемости.
    occupancy: {studio_code: visits_count}
    Транзакции с конкретной студией остаются без изменений.
    Возвращает новый список транзакций (без ОБЩ-записей).
    """
    result = []

    for t in transactions:
        studio = t['studio']

        if studio not in ('', GENERAL_ENTITY, GENERAL_NETWORK):
            result.append(t)
            continue

        # Определяем набор студий для распределения
        if studio == GENERAL_NETWORK:
            target_studios = OCCUPANCY_STUDIOS
        else:
            # ОБЩ или пустое → студии этого юрлица
            entity_studios = ENTITY_STUDIOS.get(t['entity'], [])
            target_studios = [s for s in entity_studios if s in OCCUPANCY_STUDIOS]

        total_visits = sum(occupancy.get(s, 0) for s in target_studios)
        if total_visits == 0:
            # Заполняемость не введена — оставляем как есть
            result.append(t)
            continue

        for s in target_studios:
            visits = occupancy.get(s, 0)
            if visits <= 0:
                continue
            coef = visits / total_visits
            new_t = dict(t)
            new_t['studio'] = s
            new_t['amount'] = round(t['amount'] * coef, 2)
            result.append(new_t)

    return result
