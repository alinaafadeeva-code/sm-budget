import streamlit as st
import datetime
from .mappings import MONTHS_RU


def init_period():
    """Инициализирует global_year и global_month в session_state если не заданы."""
    today = datetime.date.today()
    if 'global_year' not in st.session_state:
        st.session_state['global_year'] = today.year
    if 'global_month' not in st.session_state:
        st.session_state['global_month'] = today.month


def sidebar_period():
    """
    Рендерит выбор года и месяца в сайдбаре.
    Возвращает (year, month).
    Значения сохраняются в session_state и не сбрасываются при переходе между страницами.
    """
    init_period()
    with st.sidebar:
        st.markdown('### 📅 Период')
        year = st.number_input('Год', min_value=2024, max_value=2030, key='global_year')
        month = st.selectbox(
            'Месяц',
            options=list(MONTHS_RU.keys()),
            format_func=lambda x: MONTHS_RU[x],
            key='global_month',
        )
        st.divider()
    return int(year), month
