import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.manifold import MDS
import re
import zipfile
import io
import japanize_matplotlib  # 日本語文字化け解消用ライブラリ

st.set_page_config(page_title="Narrative Star Map Dashboard", layout="wide")

st.title("✨ 食のナラティブ・インタラクティブ星図ビュワー")
st.sidebar.header("データと表示設定")

uploaded_fixed = st.sidebar.file_uploader("ナラティブ/座標データ (Excel または CSV)", type=["xlsx", "xls", "csv"])
uploaded_demo = st.sidebar.file_uploader("イベント参加者データ (CSV)", type=["csv"])

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
            target_sheet = None
            for s in xl.sheet_names:
                if 'coordinate' in s.lower() or 'coord' in s.lower() or 'データ' in s or '座標' in s or 'sheet' in s.lower():
                    target_sheet = s
                    break
            if not target_sheet:
                target_sheet = xl.sheet_names[0]
            df_fixed = pd.read_excel(xl, sheet_name=target_sheet)
            
        df_demo = pd.read_csv(uploaded_demo)
        
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
        
        # --- UIコントロールの追加 ---
        st.sidebar.markdown("---")
        st.sidebar.subheader("表示モードの選択")
        
        # グループを選択しない（背景のみ）オプションを追加
        group_options = ["（グループを選択しない：星図のみ）"] + sorted(df_demo[group_col].unique().tolist())
        selected_group = st.sidebar.selectbox("表示する対象", group_options)
        
        show_solid = st.sidebar.checkbox("実線（自分の星座）を表示する", value=True)
        show_dotted = st.sidebar.checkbox("点線（他者への関心）を表示する", value=True)
        show_labels = st.sidebar.checkbox("カードのタイトル（星の名前）を表示する", value=True)
        
        # 描画処理
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(12, 12))
        
        # 背景の星図（全グループ共通）
        ax.scatter(df_coords['X'], df_coords['Y'], c='#FFFFFF', alpha=0.3, s=22, edgecolors='none', zorder=1)
        
        # グループが選択されている場合のみ線をプロット
        if selected_group != "（グループを選択しない：星図のみ）":
            group_data = df_demo[df_demo[group_col] == selected_group]
            colors = ['#FF0D0D', '#1E90FF', '#FFD700', '#00FF66', '#FF1493', '#00FFFF']
            
            def clean_card_string(s):
                if pd.isna(s) or str(s).strip() in ['', 'なし']:
                    return []
                cleaned = re.sub(r'[\[\]]', '', str(s))
                return [int(float(c.strip())) for c in cleaned.split(',') if c.strip().replace('.0','').isdigit()]

            related_card_nos = set()
            for idx, (_, row) in enumerate(group_data.iterrows()):
                color = colors[idx % len(colors)]
                p_id = row[part_col]
                my_cards = clean_card_string(row[my_card_col])
                interest_cards = clean_card_string(row[interest_col])
                
                # 線の表示設定に応じて関連カードを収集
                if show_solid: related_card_nos.update(my_cards)
                if show_dotted: related_card_nos.update(interest_cards)
                
                my_x = [coords_dict[c]['X'] for c in my_cards if c in coords_dict]
                my_y = [coords_dict[c]['Y'] for c in my_cards if c in coords_dict]
                if not my_x: continue
                
                cx, cy = np.mean(my_x), np.mean(my_y)
                
                # 実線がオンの場合、または点線のみの場合でも現在地（ひし形）は表示
                if show_solid or show_dotted:
                    ax.scatter([cx], [cy], c=color, marker='D', s=350, edgecolor='white', linewidth=1.5, zorder=6, label=str(p_id))
                
                # 実線の描画
                if show_solid:
                    for x, y in zip(my_x, my_y):
                        ax.plot([cx, x], [cy, y], color=color, linestyle='-', linewidth=4.0, alpha=0.9, zorder=4)
                        ax.scatter([x], [y], c=color, marker='o', s=160, edgecolor='white', linewidth=1.2, zorder=5)
                
                # 点線の描画
                if show_dotted:
                    for c in interest_cards:
                        if c in coords_dict:
                            ix, iy = coords_dict[c]['X'], coords_dict[c]['Y']
                            ax.annotate("", xy=(ix, iy), xytext=(cx, cy),
                                        arrowprops=dict(arrowstyle="-|>", color=color, linestyle=":", linewidth=2.0, alpha=0.75, shrinkA=10, shrinkB=10),
                                        zorder=3)
                            ax.scatter([ix], [iy], facecolors='none', edgecolors=color, marker='o', s=240, linewidth=2.0, zorder=2)

            # タイトルの表示
            if show_labels:
                for c_no in related_card_nos:
                    if c_no in coords_dict:
                        c_info = coords_dict[c_no]
                        ax.text(c_info['X'] + 0.05, c_info['Y'] + 0.03, f"{int(c_no)}. {c_info['見出し']}", 
                                color='#EFEFEF', fontsize=9, alpha=0.9,
                                bbox=dict(facecolor='#030305', alpha=0.75, edgecolor='none', boxstyle='round,pad=0.25'), zorder=10)
            
            ax.set_title(f'Interactive Star Map: {selected_group}', fontsize=18, color='white', pad=25)
            ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1), title="Participants", fontsize=11)
            
        else:
            # グループなし（星図のみ）の場合
            ax.set_title('Interactive Star Map: 全体星図', fontsize=18, color='white', pad=25)
            # 背景のみの場合は、すべてのタイトルを表示するか選択
            if show_labels:
                for c_no, c_info in coords_dict.items():
                    ax.text(c_info['X'] + 0.02, c_info['Y'] + 0.02, f"{int(c_no)}", 
                            color='#888888', fontsize=7, alpha=0.6, zorder=10)

        # 座標の固定と軸の非表示
        ax.set_xlim(df_coords['X'].min() - 0.3, df_coords['X'].max() + 0.3)
        ax.set_ylim(df_coords['Y'].min() - 0.3, df_coords['Y'].max() + 0.3)
        ax.axis('off')
        
        st.pyplot(fig)
        
    except Exception as e:
        st.error(f"データの処理中にエラーが発生しました: {e}")
else:
    st.info("左側のサイドバーから「ナラティブ/座標データ（Excel または CSV）」と「イベント参加者データ（CSV）」をアップロードしてください。")
