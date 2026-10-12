import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.manifold import MDS
import re
import zipfile
import io
import os
import urllib.request
import matplotlib.font_manager as fm

# --- 日本語フォント設定 ---
font_path = "ipaexg.ttf"
if not os.path.exists(font_path):
    font_url = "https://raw.githubusercontent.com/uehara1414/japanize-matplotlib/master/japanize_matplotlib/fonts/ipaexg.ttf"
    urllib.request.urlretrieve(font_url, font_path)
jp_font = fm.FontProperties(fname=font_path)

st.set_page_config(page_title="Narrative Star Map Dashboard", layout="wide")

st.title("✨ 食のナラティブ・インタラクティブ星図ビュワー")
st.sidebar.header("データと表示設定")

uploaded_fixed = st.sidebar.file_uploader("ナラティブ/座標データ (Excel または CSV)", type=["xlsx", "xls", "csv"])
uploaded_demo = st.sidebar.file_uploader("イベント参加者データ (CSV)", type=["csv"])
uploaded_summary = st.sidebar.file_uploader("グループ概況文データ (CSV) ※任意", type=["csv"]) # ★新規追加

def load_excel_safe(uploaded_file):
    try:
        return pd.ExcelFile(uploaded_file)
    except Exception as e:
        if "stylesheet" in str(e).lower() or "invalid xml" in str(e).lower():
            uploaded_file.seek(0)
            safe_io = io.BytesIO()
            with zipfile.ZipFile(uploaded_file, 'r') as zin:
                with zipfile.ZipFile(safe_io, 'w') as zout:
                    for item in zin.infolist():
                        if item.filename == 'xl/styles.xml':
                            minimal_styles = b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"></styleSheet>'
                            zout.writestr(item, minimal_styles)
                        else:
                            zout.writestr(item, zin.read(item.filename))
            safe_io.seek(0)
            return pd.ExcelFile(safe_io)
        raise e

if uploaded_fixed and uploaded_demo:
    try:
        if uploaded_fixed.name.endswith('.csv'):
            df_fixed = pd.read_csv(uploaded_fixed)
        else:
            xl = load_excel_safe(uploaded_fixed)
            target_sheet = next((s for s in xl.sheet_names if 'coordinate' in s.lower() or 'coord' in s.lower() or 'データ' in s or '座標' in s or 'sheet' in s.lower()), xl.sheet_names[0])
            df_fixed = pd.read_excel(xl, sheet_name=target_sheet)
            
        df_demo = pd.read_csv(uploaded_demo)
        
        # 概況文CSVがアップロードされている場合は読み込む
        summary_dict = {}
        if uploaded_summary:
            df_sum = pd.read_csv(uploaded_summary)
            if 'Group' in df_sum.columns and 'Summary' in df_sum.columns:
                summary_dict = pd.Series(df_sum['Summary'].values, index=df_sum['Group']).to_dict()
        
        cols_lower = [str(c).lower() for c in df_fixed.columns]
        has_precomputed_coords = any('x' in c for c in cols_lower) and any('y' in c for c in cols_lower)
        
        if has_precomputed_coords:
            x_col = [c for c in df_fixed.columns if 'x' in str(c).lower()][0]
            y_col = [c for c in df_fixed.columns if 'y' in str(c).lower()][0]
            no_col = [c for c in df_fixed.columns if 'no' in str(c).lower() or '番号' in str(c)][0]
            title_col = [c for c in df_fixed.columns if '見出し' in str(c) or 'title' in str(c).lower() or '名' in str(c)][0]
            
            df_coords = pd.DataFrame({
                'No': pd.to_numeric(df_fixed[no_col], errors='coerce'),
                '見出し': df_fixed[title_col],
                'X': pd.to_numeric(df_fixed[x_col], errors='coerce'),
                'Y': pd.to_numeric(df_fixed[y_col], errors='coerce')
            }).dropna(subset=['No'])
        else:
            val_cols = df_fixed.columns[2:12] if len(df_fixed.columns) >= 12 else df_fixed.columns[2:]
            X_data = df_fixed[val_cols].replace('評価不能', 3).apply(pd.to_numeric, errors='coerce').fillna(3)
            
            nmds = MDS(n_components=2, metric=False, random_state=42, normalized_stress='auto', max_iter=3000, eps=1e-9)
            coords = nmds.fit_transform(X_data)
            
            df_coords = pd.DataFrame({
                'No': pd.to_numeric(df_fixed.iloc[:, 0], errors='coerce'), 
                '見出し': df_fixed.iloc[:, 1], 
                'X': coords[:, 0], 
                'Y': coords[:, 1]
            }).dropna(subset=['No'])
            
        coords_dict = df_coords.set_index('No').to_dict('index')
        
        group_col = [c for c in df_demo.columns if 'group' in c.lower() or 'グループ' in c][0]
        part_col = [c for c in df_demo.columns if 'part' in c.lower() or '参加者' in c or 'id' in c.lower()][0]
        my_card_col = [c for c in df_demo.columns if 'my' in c.lower() or '選んだ' in c][0]
        interest_col = [c for c in df_demo.columns if 'interest' in c.lower() or '関心' in c][0]

        def clean_card_string(s):
            if pd.isna(s) or str(s).strip() in ['', 'なし']:
                return []
            cleaned = re.sub(r'[\[\]]', '', str(s))
            return [int(float(c.strip())) for c in cleaned.split(',') if c.strip().replace('.0','').isdigit()]

        # --- 全体の「関心（ハート）」の集計 ---
        interest_map = {}
        for _, row in df_demo.iterrows():
            interests = clean_card_string(row[interest_col])
            for c in interests:
                if c not in interest_map:
                    interest_map[c] = []
                interest_map[c].append(f"{row[group_col]} {row[part_col]}")
        
        st.sidebar.markdown("---")
        st.sidebar.subheader("表示モードの選択")
        
        group_options = ["（グループを選択しない：星図のみ）"] + sorted(df_demo[group_col].unique().tolist())
        selected_group = st.sidebar.selectbox("表示する対象", group_options)
        
        show_solid = st.sidebar.checkbox("実線（自分の星座）を表示する", value=True)
        show_dotted = st.sidebar.checkbox("点線（他者への関心）を表示する", value=True)
        show_labels = st.sidebar.checkbox("カードのタイトル（星の名前）を表示する", value=True)
        show_hearts = st.sidebar.checkbox("他者からの関心(♥)を表示する", value=True)
        
        # ▼ グループ概況テキストの表示（CSVから動的に取得）
        if selected_group != "（グループを選択しない：星図のみ）":
            summary_text = summary_dict.get(selected_group, "このグループの概況文ファイル（CSV）がアップロードされていないか、該当グループのデータがありません。")
            st.info(f"**【{selected_group} の特徴・概況】**\n\n{summary_text}")
        
        # 描画処理
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(13, 13))
        
        ax.scatter(df_coords['X'], df_coords['Y'], c='#FFFFFF', alpha=0.3, s=22, edgecolors='none', zorder=1)
        
        related_card_nos = set()
        
        if selected_group != "（グループを選択しない：星図のみ）":
            group_data = df_demo[df_demo[group_col] == selected_group]
            colors = ['#FF0D0D', '#1E90FF', '#FFD700', '#00FF66', '#FF1493', '#00FFFF']
            
            for idx, (_, row) in enumerate(group_data.iterrows()):
                color = colors[idx % len(colors)]
                p_id = row[part_col]
                my_cards = clean_card_string(row[my_card_col])
                interest_cards = clean_card_string(row[interest_col])
                
                if show_solid: related_card_nos.update(my_cards)
                if show_dotted: related_card_nos.update(interest_cards)
                
                my_x = [coords_dict[c]['X'] for c in my_cards if c in coords_dict]
                my_y = [coords_dict[c]['Y'] for c in my_cards if c in coords_dict]
                if not my_x: continue
                
                cx, cy = np.mean(my_x), np.mean(my_y)
                
                if show_solid or show_dotted:
                    ax.scatter([cx], [cy], c=color, marker='D', s=350, edgecolor='white', linewidth=1.5, zorder=6, label=str(p_id))
                
                if show_solid:
                    for x, y in zip(my_x, my_y):
                        ax.plot([cx, x], [cy, y], color=color, linestyle='-', linewidth=4.0, alpha=0.9, zorder=4)
                        ax.scatter([x], [y], c=color, marker='o', s=160, edgecolor='white', linewidth=1.2, zorder=5)
                
                if show_dotted:
                    for c in interest_cards:
                        if c in coords_dict:
                            ix, iy = coords_dict[c]['X'], coords_dict[c]['Y']
                            ax.annotate("", xy=(ix, iy), xytext=(cx, cy),
                                        arrowprops=dict(arrowstyle="-|>", color=color, linestyle=":", linewidth=2.0, alpha=0.75, shrinkA=10, shrinkB=10),
                                        zorder=3)
                            ax.scatter([ix], [iy], facecolors='none', edgecolors=color, marker='o', s=240, linewidth=2.0, zorder=2)

            ax.set_title(f'Interactive Star Map: {selected_group}', fontsize=20, color='white', pad=25, fontproperties=jp_font)
            ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1), title="Participants", prop=jp_font)
            
        else:
            ax.set_title('Interactive Star Map: 全体星図', fontsize=20, color='white', pad=25, fontproperties=jp_font)
            related_card_nos = set(coords_dict.keys())

        # ▼ タイトルとハート(♥)の描画
        for c_no in related_card_nos:
            if c_no in coords_dict:
                c_info = coords_dict[c_no]
                if show_labels:
                    label_text = f"{int(c_no)}" if selected_group == "（グループを選択しない：星図のみ）" else f"{int(c_no)}. {c_info['見出し']}"
                    label_size = 7 if selected_group == "（グループを選択しない：星図のみ）" else 10
                    bbox_style = None if selected_group == "（グループを選択しない：星図のみ）" else dict(facecolor='#030305', alpha=0.8, edgecolor='none', boxstyle='round,pad=0.25')
                    
                    ax.text(c_info['X'] + 0.05, c_info['Y'] + 0.03, label_text, 
                            color='#EFEFEF', fontsize=label_size, alpha=0.95, fontproperties=jp_font,
                            bbox=bbox_style, zorder=10)
                
                if show_hearts and c_no in interest_map:
                    heart_count = len(interest_map[c_no])
                    ax.text(c_info['X'] - 0.12, c_info['Y'] + 0.08, f"♥ {heart_count}", 
                            color='#FF69B4', fontsize=12, fontweight='bold', fontproperties=jp_font, zorder=11)

        ax.set_xlim(df_coords['X'].min() - 0.3, df_coords['X'].max() + 0.3)
        ax.set_ylim(df_coords['Y'].min() - 0.3, df_coords['Y'].max() + 0.3)
        ax.axis('off')
        
        st.pyplot(fig)
        
        # ▼ 関心の詳細データ表
        if show_hearts and selected_group != "（グループを選択しない：星図のみ）":
            st.markdown("### 💖 このグループの対話で関心を集めた星の詳細")
            interest_data = []
            for c_no in sorted(list(related_card_nos)):
                if c_no in interest_map:
                    c_info = coords_dict[c_no]
                    interest_data.append({
                        "No": int(c_no),
                        "星のタイトル": c_info['見出し'],
                        "関心の数 (♥)": len(interest_map[c_no]),
                        "関心を寄せた人": ", ".join(interest_map[c_no])
                    })
            
            if interest_data:
                st.dataframe(pd.DataFrame(interest_data), use_container_width=True)
            else:
                st.info("現在表示されている星には、まだ関心が寄せられていません。")
        
    except Exception as e:
        st.error(f"データの処理中にエラーが発生しました: {e}")
else:
    st.info("左側のサイドバーから「ナラティブ/座標データ」「イベント参加者データ」、および「グループ概況文データ（CSV）」をアップロードしてください。")
