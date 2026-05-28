import streamlit as st
from PIL import Image

_icon = Image.open('assets/logo.png')

st.set_page_config(
    page_title='SMSTRETCHING — Бюджет',
    page_icon=_icon,
    layout='wide',
    initial_sidebar_state='expanded',
)

st.title('💪 SMSTRETCHING — Бюджет 2026')
st.markdown('''
Добро пожаловать в систему управления бюджетом **SMSTRETCHING / СМ Групп**.

Используй меню слева для навигации:

| Раздел | Описание |
|--------|----------|
| 📤 Загрузить реестр | Ежедневная загрузка платёжных реестров |
| 💰 Доходы | Ввод выручки по студиям |
| 👥 Заполняемость | Данные о посещаемости для распределения общих расходов |
| 👔 Зарплаты | Ежемесячный ввод данных по зарплатам |
| 📊 Дашборд | Аналитика: факт vs план, по студиям, по статьям |
''')
