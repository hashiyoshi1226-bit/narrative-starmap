import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.manifold import MDS
import re
import matplotlib.font_manager as fm

st.set_page_config(page_title="Narrative Star Map Dashboard", layout="wide")

st.title("✨ 食のナラティブ・インタラクティブ星図ビュワー")
st.sidebar.header("データと表示設定")

# 1. エクセル・CSVファイルのアップロード機能
uploaded_fixed = st.sidebar.file_uploader("価値観データ (fixed.xlsx)", type=["xlsx"])
uploaded_demo = st.sidebar.file_uploader("イベント参加者データ (csv)", type=["csv"])

if uploaded_fixed and uploaded_demo:
    # データの読み込み
    df_fixed = pd.read_excel(uploaded_fixed, sheet_name='データ貼り付け', usecols="A:L")
    df_demo = pd.read_csv(uploaded_demo)
    
    # 座標計算（非計量MDS）
    val_cols = df_fixed.columns[2:]
    X = df_fixed[val_cols].replace('評価不能', 3).astype(float)
    nmds = MDS(n_components=2, metric=False, random_state=42, normalized_stress='auto', max_iter=3000, eps=1e-9)
    coords = nmds.fit_transform(X)
    df_coords = pd.DataFrame({'No': df_fixed['No'], '見出し': df_fixed['見出し'], 'X': coords[:, 0], 'Y': coords[:, 1]})
    coords_dict = df_coords.set_index('No').to_dict('index')
    
    # 2. インタラクティブなコントロール（グループ選択）
    selected_group = st.sidebar.selectbox("表示するグループを選択", sorted(df_demo['Group'].unique()))
    show_dialogue_lines = st.sidebar.checkbox("対話のつながり（点線矢印）を表示する", value=True)
    show_titles = st.sidebar.checkbox("カードのタイトルを表示する", value=True)
    
    # 描画処理
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 10))
    
    # 背景の星図
    ax.scatter(df_coords['X'], df_coords['Y'], c='#FFFFFF', alpha=0.3, s=20, edgecolors='none', zorder=1)
    
    group_data = df_demo[df_demo['Group'] == selected_group]
    colors = ['#FF0D0D', '#1E90FF', '#FFD700', '#00FF66', '#FF1493', '#00FFFF']
    
    def clean_card_string(s):
        if pd.isna(s) or str(s).strip() in ['', 'なし']:
            return []
        cleaned = re.sub(r'[\[\]]', '', str(s))
        return [int(c.strip()) for c in cleaned.split(',') if c.strip().isdigit()]

    related_card_nos = set()
    for idx, (_, row) in enumerate(group_data.iterrows()):
        color = colors[idx % len(colors)]
        p_id = row['Participant']
        my_cards = clean_card_string(row['My_Cards'])
        interest_cards = clean_card_string(row['Interest_Cards']) if show_dialogue_lines else []
        
        related_card_nos.update(my_cards)
        related_card_nos.update(interest_cards)
        
        my_x = [coords_dict[c]['X'] for c in my_cards if c in coords_dict]
        my_y = [coords_dict[c]['Y'] for c in my_cards if c in coords_dict]
        if not my_x: continue
        
        cx, cy = np.mean(my_x), np.mean(my_y)
        ax.scatter([cx], [cy], c=color, marker='D', s=300, edgecolor='white', linewidth=1.5, zorder=6, label=p_id)
        
        for x, y in zip(my_x, my_y):
            ax.plot([cx, x], [cy, y], color=color, linestyle='-', linewidth=3.5, alpha=0.9, zorder=4)
            ax.scatter([x], [y], c=color, marker='o', s=140, edgecolor='white', linewidth=1, zorder=5)
            
        if show_dialogue_lines:
            for c in interest_cards:
                if c in coords_dict:
                    ix, iy = coords_dict[c]['X'], coords_dict[c]['Y']
                    ax.annotate("", xy=(ix, iy), xytext=(cx, cy),
                                arrowprops=dict(arrowstyle="-|>", color=color, linestyle=":", linewidth=2.0, alpha=0.75, shrinkA=10, shrinkB=10),
                                zorder=3)
                    ax.scatter([ix], [iy], facecolors='none', edgecolors=color, marker='o', s=200, linewidth=2.0, zorder=2)

    if show_titles:
        for c_no in related_card_nos:
            if c_no in coords_dict:
                c_info = coords_dict[c_no]
                ax.text(c_info['X'] + 0.05, c_info['Y'] + 0.03, f"{c_no}. {c_info['見出し']}", 
                        color='#EFEFEF', fontsize=8.5, alpha=0.9,
                        bbox=dict(facecolor='#030305', alpha=0.75, edgecolor='none', boxstyle='round,pad=0.2'), zorder=10)

    ax.set_title(f'Interactive Star Map: {selected_group}', fontsize=16, color='white', pad=20)
    ax.set_xlim(df_coords['X'].min() - 0.3, df_coords['X'].max() + 0.3)
    ax.set_ylim(df_coords['Y'].min() - 0.3, df_coords['Y'].max() + 0.3)
    ax.axis('off')
    ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1), title="Participants", fontsize=10)
    
    st.pyplot(fig)
else:
    st.info("左側のサイドバーから「fixed.xlsx」と「イベント参加者データ（CSV）」をアップロードしてください。")
