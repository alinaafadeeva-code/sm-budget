import streamlit as st
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from utils.processor import process_registry, detect_entity, apply_occupancy
from utils.sheets import save_expenses, get_occupancy_dict, clear_caches
from utils.mappings import ENTITY_NAMES, STUDIO_CODES, MONTHS_RU, ALL_EXPENSE_CATEGORIES

st.set_page_config(page_title='Загрузить реестр', page_icon='📤', layout='wide')
st.title('📤 Загрузить реестр платежей')

uploaded = st.file_uploader(
    'Выбери Excel-файл реестра',
    type=['xlsx', 'xls'],
    help='Файл должен быть в формате банковского реестра (ИПМ, ИПК, СМГ или СМЛ)',
)

if uploaded:
    # Определяем юрлицо
    detected = detect_entity(uploaded.name)
    col1, col2 = st.columns([1, 2])
    with col1:
        entity = st.selectbox(
            'Юридическое лицо',
            options=list(ENTITY_NAMES.keys()),
            index=list(ENTITY_NAMES.keys()).index(detected) if detected else 0,
            format_func=lambda x: f'{x} — {ENTITY_NAMES[x]}',
        )
    if detected and detected == entity:
        st.success(f'✅ Юрлицо определено автоматически: **{ENTITY_NAMES[entity]}**')
    elif detected and detected != entity:
        st.warning('⚠️ Юрлицо изменено вручную')

    # Парсим файл
    with st.spinner('Читаю файл…'):
        transactions = process_registry(uploaded, entity)

    if not transactions:
        st.error('Не удалось найти транзакции в файле. Проверь формат.')
        st.stop()

    st.success(f'Найдено транзакций: **{len(transactions)}**')

    # Предпросмотр
    df_preview = pd.DataFrame(transactions)
    df_preview['category_name'] = df_preview['category_code'].map(
        lambda x: ALL_EXPENSE_CATEGORIES.get(int(x), f'Статья {x}') if pd.notna(x) else '—'
    )
    df_preview['studio_name'] = df_preview['studio'].map(
        lambda x: STUDIO_CODES.get(x, x) if x else '(общие)'
    )
    df_preview['month_name'] = df_preview['month'].map(MONTHS_RU)

    st.subheader('Предпросмотр')
    st.dataframe(
        df_preview[['date', 'month_name', 'studio_name', 'category_name', 'amount', 'description']].rename(columns={
            'date': 'Дата', 'month_name': 'Месяц', 'studio_name': 'Студия',
            'category_name': 'Статья', 'amount': 'Сумма', 'description': 'Описание',
        }),
        use_container_width=True,
        height=350,
    )

    # Статистика по студиям
    general_count = sum(1 for t in transactions if t['studio'] in ('', 'ОБЩ', 'ОБЩ СЕТЬ'))
    if general_count > 0:
        st.info(
            f'ℹ️ **{general_count} транзакций** помечены как «общие» — '
            'они будут разнесены по студиям после ввода заполняемости за этот месяц.'
        )

    # Итог по студиям
    with st.expander('📊 Итог по студиям'):
        summary = df_preview.groupby('studio_name')['amount'].sum().reset_index()
        summary.columns = ['Студия', 'Сумма']
        summary = summary.sort_values('Сумма', ascending=False)
        st.dataframe(summary, use_container_width=True)

    # Кнопка сохранения
    st.divider()
    if st.button('💾 Сохранить в базу', type='primary', use_container_width=True):
        with st.spinner('Сохраняю…'):
            # Применяем заполняемость к общим расходам, если она есть
            months = list({t['month'] for t in transactions})
            year = transactions[0]['year']
            all_records = []
            for month in months:
                month_txns = [t for t in transactions if t['month'] == month]
                occ = get_occupancy_dict(year, month)
                if occ:
                    month_txns = apply_occupancy(month_txns, occ)
                all_records.extend(month_txns)
            save_expenses(all_records)
            clear_caches()
        st.success('✅ Реестр успешно сохранён!')
        st.balloons()
