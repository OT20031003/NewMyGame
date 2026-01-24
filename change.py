import os

# 対象ファイルのパス
html_path = 'templates/country_detail.html'

# ファイルが存在するかチェック（カレントディレクトリ直下の場合のフォールバック）
if not os.path.exists(html_path):
    html_path = 'templates/country_detail.html'

with open(html_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. ヘッダーへのボタン追加
# "Back to World" ボタンの直前に "Last 100 Turns" ボタンを挿入します
button_html = """
            <button id="toggleHistoryBtn" class="btn-back" style="background-color: var(--accent-color); margin-right: 1rem;">
                <i class="fas fa-history"></i> Last 100 Turns
            </button>
"""
target_anchor = '<a href="{{ url_for(\'index\') }}" class="btn-back">'

if "id=\"toggleHistoryBtn\"" not in content:
    # target_anchor の前にボタンを挿入
    content = content.replace(target_anchor, button_html + target_anchor)
    print("Added button HTML.")

# 2. JavaScriptロジックの追加
# 既存のスクリプトの末尾付近（モーダル閉じる処理の前）にロジックを挿入します
js_logic = """
        // --- Toggle History Logic (Last 100 Turns) ---
        let isLast100Mode = false;
        const toggleHistoryBtn = document.getElementById('toggleHistoryBtn');

        if (toggleHistoryBtn) {
            toggleHistoryBtn.addEventListener('click', () => {
                isLast100Mode = !isLast100Mode;
                updateChartsHistoryRange();
                
                // Update Button Visual State
                if (isLast100Mode) {
                    toggleHistoryBtn.innerHTML = '<i class="fas fa-globe"></i> Show All History';
                    toggleHistoryBtn.style.backgroundColor = 'var(--primary-color)';
                } else {
                    toggleHistoryBtn.innerHTML = '<i class="fas fa-history"></i> Last 100 Turns';
                    toggleHistoryBtn.style.backgroundColor = 'var(--accent-color)';
                }
            });
        }

        // 配列を末尾からcount個だけ切り出すヘルパー関数
        function sliceData(dataArray, count) {
            if (!isLast100Mode) return dataArray;
            if (dataArray.length <= count) return dataArray;
            return dataArray.slice(dataArray.length - count);
        }

        function updateChartsHistoryRange() {
            const count = 100;
            
            // シンプルなラインチャートを更新する内部関数
            const updateLineChart = (chart, data, labels) => {
                if (!chart) return;
                chart.data.datasets[0].data = sliceData(data, count);
                // ラベルもデータ数に合わせてスライス（データの長さに合わせるのが安全）
                const currentDataLen = chart.data.datasets[0].data.length;
                chart.data.labels = labels.slice(labels.length - currentDataLen);
                chart.update();
            };

            // 1. Population History
            updateLineChart(chartInstances.populationHistoryChart, pastPopulationData, gdpLabels);

            // 2. Exchange Rate
            updateLineChart(chartInstances.exchangeRateChart, exchangeRateValues, exchangeRateLabels);

            // 3. GDP (Loc)
            updateLineChart(chartInstances.gdpChart, gdpValues, gdpLabels);

            // 4. GDP (USD)
            updateLineChart(chartInstances.usdgdpChart, usdGdpValues, gdpLabels);

            // 5. GDP Per Capita (USD)
            // データ配列自体が異なる長さの可能性があるため、元のラベル配列をスライスして渡す
            updateLineChart(chartInstances.gdpPerCapitaUsdChart, gdpPerCapitaUsdData, gdpLabels.slice(0, gdpPerCapitaUsdData.length));

            // 6. Real Interest Diff
            updateLineChart(chartInstances.realInterestDiffChart, realInterestDiffValues, gdpLabels.slice(0, realInterestDiffValues.length));

            // 7. Price Inflation
            updateLineChart(chartInstances.priceChart, priceInflationData, inflationLabels);

            // 8. Industry History
            updateLineChart(chartInstances.industryData, industryData, gdpLabels);

            // 9. Debt / GDP Ratio
            updateLineChart(chartInstances.debtChart, debtRatioData, gdpLabels.slice(0, debtRatioData.length));

            // 10. Rate & Interest Correlation (2軸チャート)
            const corrChart = chartInstances.rateDiffCorrelationChart;
            if (corrChart) {
                // Dataset 0: Real Interest Diff
                corrChart.data.datasets[0].data = sliceData(realInterestDiffValues, count);
                // Dataset 1: Exchange Rate
                corrChart.data.datasets[1].data = sliceData(exchangeRateValues, count);
                
                // Labels (Exchange Rate Labels)
                const dataLen = corrChart.data.datasets[1].data.length;
                corrChart.data.labels = exchangeRateLabels.slice(exchangeRateLabels.length - dataLen);
                
                corrChart.update();
            }
        }
"""

target_js_marker = 'document.querySelector(".close-button").onclick = closeModal;'

if "// --- Toggle History Logic (Last 100 Turns) ---" not in content:
    if target_js_marker in content:
        content = content.replace(target_js_marker, js_logic + '\n        ' + target_js_marker)
        print("Added JS logic.")
    else:
        print("Error: Target JS marker not found. Could not inject JS.")

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"Updated {html_path}")