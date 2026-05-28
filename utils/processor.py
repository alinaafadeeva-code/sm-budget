import pandas as pd
import re
from datetime import datetime
from .mappings import (
    STUDIO_CODES, STUDIO_ALIASES, ENTITY_STUDIOS, STUDIO_ENTITY,
    GENERAL_ENTITY, GENERAL_NETWORK, OCCUPANCY_STUDIOS,
    AUTO_DISTRIBUTE_CATEGORIES,
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


def _parse_single_studio(upper: str):
    """Возвращает код студии или None если не распознано."""
    if upper in STUDIO_CODES:
        return upper
    if upper in STUDIO_ALIASES:
        return STUDIO_ALIASES[upper]
    for alias, code in STUDIO_ALIASES.items():
        if alias in upper:
            return code
    for code in STUDIO_CODES:
        if code in upper:
            return code
    return None


def normalize_studio(raw: str) -> str:
    """
    Приводит комментарий к стандартному коду студии.
    Возвращает:
      - код студии (ПК1, ЧП, …)
      - 'ПМ|ЧП'     — несколько студий через | → делить по заполняемости между ними
      - 'ОБЩ'       — делить по юрлицу
      - 'ОБЩ СЕТЬ'  — делить по всей сети
      - ''           — пустое → будет трактоваться как ОБЩ
    """
    if not raw or str(raw).strip().lower() in ('nan', '', '0'):
        return ''
    upper = str(raw).strip().upper()
    if upper == GENERAL_NETWORK.upper():
        return GENERAL_NETWORK
    if upper == GENERAL_ENTITY.upper():
        return GENERAL_ENTITY

    # Сначала ищем несколько студий — это важно делать ДО одиночного поиска,
    # чтобы подстрочный поиск ('ЧП' в 'ПМ И ЧП') не давал ложный результат
    parts = re.split(r'[,/\+]|\s+И\s+|\s+', upper)
    parts = [p.strip() for p in parts if p.strip() and p.strip() != 'И']
    if len(parts) > 1:
        found = []
        for part in parts:
            code = _parse_single_studio(part)
            if code and code not in found:
                found.append(code)
        if len(found) > 1:
            return '|'.join(found)  # например 'ПМ|ЧП'
        if len(found) == 1:
            return found[0]

    # Проверяем одиночный код (точное совпадение, потом подстрока)
    single = _parse_single_studio(upper)
    if single:
        return single

    return upper  # вернём как есть


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


def _detect_format(df: pd.DataFrame) -> dict:
    """
    Определяет формат реестра по заголовкам и возвращает индексы колонок.
    Короткий формат (7 колонок): №, Дата, Сумма, Информация, Назначение, Студия, Статья
    Банковский формат (13 колонок): №, Дата, Документ, Номер, Сумма, ..., Студия, Статья
    """
    # Ищем строку с заголовками
    for row_idx in range(min(5, len(df))):
        row_vals = [str(v).strip().lower() for v in df.iloc[row_idx]]
        if 'сумма' in row_vals or 'дата' in row_vals:
            headers = [str(v).strip() for v in df.iloc[row_idx]]
            h_lower = [h.lower() for h in headers]

            def find(keywords):
                for kw in keywords:
                    for i, h in enumerate(h_lower):
                        if kw in h:
                            return i
                return None

            return {
                'header_row': row_idx,
                'col_date':   find(['дата']),
                'col_amount': find(['сумма']),
                'col_desc':   find(['назначение']),
                'col_studio': find(['студия', 'комментарий']),
                'col_cat':    find(['статья']),
            }

    # Если заголовки не найдены — угадываем по количеству колонок
    ncols = df.shape[1]
    if ncols <= 8:
        # Короткий формат: №, Дата, Сумма, Инфо, Назначение, Студия, Статья
        return {'header_row': None, 'col_date': 1, 'col_amount': 2,
                'col_desc': 4, 'col_studio': 5, 'col_cat': 6}
    else:
        # Банковский формат
        return {'header_row': None, 'col_date': 1, 'col_amount': 4,
                'col_desc': 6, 'col_studio': 11, 'col_cat': 12}


def process_registry(file_obj, entity: str) -> list[dict]:
    """
    Читает Excel-реестр и возвращает список транзакций.
    Поддерживает два формата: короткий (7 колонок) и банковский (13 колонок).
    """
    df = pd.read_excel(file_obj, header=None, dtype=str)
    fmt = _detect_format(df)
    transactions = []

    for row_idx, (_, row) in enumerate(df.iterrows()):
        # Пропускаем строку заголовков
        if fmt['header_row'] is not None and row_idx == fmt['header_row']:
            continue

        val0 = str(row.iloc[0]).strip()

        # Пропускаем строки-заголовки и итоги
        if val0.lower() in ('nan', '', '№ п/п', 'итого', '№'):
            continue

        # Строка с данными — первая колонка должна быть числом
        try:
            int(float(val0))
        except (ValueError, TypeError):
            continue

        # Дата
        date_raw = row.iloc[fmt['col_date']] if fmt['col_date'] is not None else None
        try:
            date = pd.to_datetime(date_raw)
        except Exception:
            continue

        # Сумма
        amount = parse_amount(row.iloc[fmt['col_amount']]) if fmt['col_amount'] is not None else 0
        if amount <= 0:
            continue

        # Студия
        col_s = fmt['col_studio']
        comment_raw = str(row.iloc[col_s]).strip() if col_s is not None and col_s < len(row) else ''
        studio = normalize_studio(comment_raw)

        # Статья (пустое поле = 0, т.е. "без статьи, не разносить")
        col_c = fmt['col_cat']
        cat_raw = row.iloc[col_c] if col_c is not None and col_c < len(row) else None
        try:
            category_code = int(float(str(cat_raw)))
        except (ValueError, TypeError):
            category_code = 0

        # Описание
        col_d = fmt['col_desc']
        description = str(row.iloc[col_d]).strip() if col_d is not None and col_d < len(row) else ''
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

        # Статьи 44 и 45 (налоги) всегда делятся по всей сети
        if t.get('category_code') in AUTO_DISTRIBUTE_CATEGORIES:
            studio = GENERAL_NETWORK

        # Несколько студий через | → делим по заполняемости между ними
        if '|' in studio:
            target_studios = studio.split('|')
            total_visits = sum(occupancy.get(s, 0) for s in target_studios)
            if total_visits == 0:
                # Нет данных заполняемости — делим поровну
                share = round(t['amount'] / len(target_studios), 2)
                for s in target_studios:
                    new_t = dict(t)
                    new_t['studio'] = s
                    new_t['amount'] = share
                    result.append(new_t)
            else:
                for s in target_studios:
                    visits = occupancy.get(s, 0)
                    if visits <= 0:
                        continue
                    new_t = dict(t)
                    new_t['studio'] = s
                    new_t['amount'] = round(t['amount'] * visits / total_visits, 2)
                    result.append(new_t)
            continue

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
