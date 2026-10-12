#include "screens/chanlun/ChanlunScreen.h"

#include "python/PythonRunner.h"
#include "ui/theme/Theme.h"

#include <algorithm>

#include <QFile>
#include <QFileDialog>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QPainter>
#include <QPointer>
#include <QPushButton>
#include <QRegularExpression>
#include <QTableWidget>
#include <QVBoxLayout>

namespace fincept::screens {

namespace {

QString signal_label(const QString& type) {
    if (type == "buy1")
        return QStringLiteral("一买");
    if (type == "buy2")
        return QStringLiteral("二买");
    if (type == "buy3")
        return QStringLiteral("三买");
    if (type == "sell1")
        return QStringLiteral("一卖");
    if (type == "sell2")
        return QStringLiteral("二卖");
    if (type == "sell3")
        return QStringLiteral("三卖");
    return type;
}

QJsonArray bars_from_csv(const QString& text, QString* error) {
    QJsonArray bars;
    const QStringList lines = text.split(QRegularExpression("[\r\n]+"));
    for (const QString& raw_line : lines) {
        const QString line = raw_line.trimmed();
        if (line.isEmpty() || line.startsWith('#'))
            continue;
        const QStringList parts = line.split(QRegularExpression("[,;\\t\\s]+"), Qt::SkipEmptyParts);
        QVector<double> nums;
        nums.reserve(parts.size());
        for (const QString& part : parts) {
            bool ok = false;
            const double value = part.toDouble(&ok);
            if (ok)
                nums.push_back(value);
        }
        if (nums.size() < 4)
            continue;
        int start = 0;
        if (nums.size() >= 5 && nums[0] > 19000000.0)
            start = 1;
        if (nums.size() - start < 4)
            continue;
        QJsonObject bar;
        bar["o"] = nums[start];
        bar["h"] = nums[start + 1];
        bar["l"] = nums[start + 2];
        bar["c"] = nums[start + 3];
        bars.append(bar);
    }
    if (bars.size() < 10 && error)
        *error = QStringLiteral("CSV 里可用的 K 线不足 10 根。需要 open,high,low,close。");
    return bars;
}

} // namespace

class ChanlunChart : public QWidget {
  public:
    explicit ChanlunChart(QWidget* parent = nullptr) : QWidget(parent) { setMinimumHeight(280); }

    void set_result(const QJsonObject& result) {
        bars_ = result.value("bars").toArray();
        bi_ = result.value("bi").toArray();
        pivots_ = result.value("zhongshu").toArray();
        signals_ = result.value("signals").toArray();
        update();
    }

  protected:
    void paintEvent(QPaintEvent*) override {
        QPainter p(this);
        p.fillRect(rect(), QColor(ui::colors::BG_BASE()));
        if (bars_.isEmpty()) {
            p.setPen(QColor(ui::colors::TEXT_DIM()));
            p.drawText(rect(), Qt::AlignCenter, QStringLiteral("运行示例，或打开 CSV"));
            return;
        }

        double lo = 1e300;
        double hi = -1e300;
        for (const QJsonValue& value : bars_) {
            const QJsonObject bar = value.toObject();
            lo = std::min(lo, bar.value("l").toDouble());
            hi = std::max(hi, bar.value("h").toDouble());
        }
        if (!(hi > lo)) {
            hi = lo + 1.0;
        }
        const double pad = 16.0;
        const double width = std::max(1.0, double(this->width()) - pad * 2.0);
        const double height = std::max(1.0, double(this->height()) - pad * 2.0);
        const int n = bars_.size();
        auto x_of = [&](int index) {
            if (n <= 1)
                return pad + width / 2.0;
            return pad + width * double(std::max(0, std::min(index, n - 1))) / double(n - 1);
        };
        auto y_of = [&](double price) { return pad + height * (hi - price) / (hi - lo); };

        p.setPen(Qt::NoPen);
        p.setBrush(QColor(255, 180, 40, 28));
        for (const QJsonValue& value : pivots_) {
            const QJsonObject pivot = value.toObject();
            const double x1 = x_of(pivot.value("start").toInt());
            const double x2 = x_of(pivot.value("end").toInt());
            const double y1 = y_of(pivot.value("zg").toDouble());
            const double y2 = y_of(pivot.value("zd").toDouble());
            p.drawRect(QRectF(std::min(x1, x2), std::min(y1, y2), std::abs(x2 - x1), std::abs(y2 - y1)));
        }

        const double candle_w = std::max(1.0, width / std::max(n, 1) * 0.6);
        for (int i = 0; i < n; ++i) {
            const QJsonObject bar = bars_.at(i).toObject();
            const double open = bar.value("o").toDouble();
            const double close = bar.value("c").toDouble();
            const bool up = close >= open;
            const QColor color = QColor(up ? ui::colors::POSITIVE() : ui::colors::NEGATIVE());
            p.setPen(color);
            const double x = x_of(i);
            p.drawLine(QPointF(x, y_of(bar.value("h").toDouble())), QPointF(x, y_of(bar.value("l").toDouble())));
            p.setBrush(up ? Qt::NoBrush : QBrush(color));
            const double y_open = y_of(open);
            const double y_close = y_of(close);
            p.drawRect(QRectF(x - candle_w / 2.0, std::min(y_open, y_close), candle_w,
                              std::max(1.0, std::abs(y_close - y_open))));
        }

        const QColor amber(ui::colors::AMBER());
        QPen bi_pen(amber);
        bi_pen.setWidthF(1.4);
        p.setPen(bi_pen);
        p.setBrush(Qt::NoBrush);
        for (const QJsonValue& value : bi_) {
            const QJsonObject bi = value.toObject();
            p.drawLine(QPointF(x_of(bi.value("start").toInt()), y_of(bi.value("start_price").toDouble())),
                       QPointF(x_of(bi.value("end").toInt()), y_of(bi.value("end_price").toDouble())));
        }

        for (const QJsonValue& value : signals_) {
            const QJsonObject sig = value.toObject();
            const bool buy = sig.value("type").toString().startsWith("buy");
            p.setPen(Qt::NoPen);
            p.setBrush(QColor(buy ? ui::colors::POSITIVE() : ui::colors::NEGATIVE()));
            const QPointF at(x_of(sig.value("index").toInt()), y_of(sig.value("price").toDouble()));
            p.drawEllipse(at, 4.0, 4.0);
            p.setPen(QColor(ui::colors::TEXT_PRIMARY()));
            p.drawText(at + QPointF(6.0, buy ? 12.0 : -6.0), signal_label(sig.value("type").toString()));
        }
    }

  private:
    QJsonArray bars_;
    QJsonArray bi_;
    QJsonArray pivots_;
    QJsonArray signals_;
};

ChanlunScreen::ChanlunScreen(QWidget* parent) : QWidget(parent) {
    setStyleSheet(QString("background:%1;").arg(ui::colors::BG_BASE()));
    auto* root = new QVBoxLayout(this);
    root->setContentsMargins(12, 10, 12, 10);
    root->setSpacing(8);

    auto* header = new QHBoxLayout;
    auto* title = new QLabel(QStringLiteral("缠论"));
    title->setStyleSheet(QString("color:%1;font-size:16px;font-weight:700;background:transparent;")
                             .arg(ui::colors::AMBER()));
    header->addWidget(title);
    header->addStretch();
    sample_btn_ = new QPushButton(QStringLiteral("运行示例"));
    csv_btn_ = new QPushButton(QStringLiteral("打开 CSV"));
    const QString button_style = QString("QPushButton{color:%1;background:%2;border:1px solid %3;padding:4px 10px;}"
                                         "QPushButton:hover{border-color:%1;}")
                                     .arg(ui::colors::TEXT_PRIMARY(), ui::colors::BG_RAISED(), ui::colors::BORDER_MED());
    sample_btn_->setStyleSheet(button_style);
    csv_btn_->setStyleSheet(button_style);
    connect(sample_btn_, &QPushButton::clicked, this, &ChanlunScreen::run_sample);
    connect(csv_btn_, &QPushButton::clicked, this, &ChanlunScreen::run_csv);
    header->addWidget(sample_btn_);
    header->addWidget(csv_btn_);
    root->addLayout(header);

    note_ = new QLabel(QStringLiteral(
        "本地计算分型、笔、线段、中枢和一二三买卖点。bbfamily/abu 的开源树没有缠论代码，"
        "这里按公开的缠论规则实现，不连接 Fincept Enterprise。"));
    note_->setWordWrap(true);
    note_->setStyleSheet(QString("color:%1;background:transparent;").arg(ui::colors::TEXT_SECONDARY()));
    root->addWidget(note_);

    chart_ = new ChanlunChart(this);
    root->addWidget(chart_, 1);

    table_ = new QTableWidget(0, 4, this);
    table_->setHorizontalHeaderLabels({QStringLiteral("信号"), QStringLiteral("K线"), QStringLiteral("价格"),
                                       QStringLiteral("说明")});
    table_->horizontalHeader()->setStretchLastSection(true);
    table_->verticalHeader()->setVisible(false);
    table_->setEditTriggers(QAbstractItemView::NoEditTriggers);
    table_->setSelectionBehavior(QAbstractItemView::SelectRows);
    table_->setMinimumHeight(140);
    root->addWidget(table_);

    status_ = new QLabel(QStringLiteral("尚未计算"));
    status_->setStyleSheet(QString("color:%1;background:transparent;").arg(ui::colors::TEXT_TERTIARY()));
    root->addWidget(status_);
}

void ChanlunScreen::set_busy(bool busy) {
    sample_btn_->setEnabled(!busy);
    csv_btn_->setEnabled(!busy);
    if (busy)
        status_->setText(QStringLiteral("计算中…"));
}

void ChanlunScreen::apply_json(const QString& json_text, const QString& error) {
    set_busy(false);
    if (!error.isEmpty()) {
        status_->setText(error);
        return;
    }
    const QJsonDocument doc = QJsonDocument::fromJson(python::extract_json(json_text).toUtf8());
    const QJsonObject obj = doc.object();
    if (obj.contains("error")) {
        status_->setText(obj.value("error").toString());
        return;
    }
    if (!obj.contains("bi")) {
        status_->setText(QStringLiteral("没有读到缠论结果"));
        return;
    }
    chart_->set_result(obj);
    const QJsonArray marks = obj.value("signals").toArray();
    table_->setRowCount(marks.size());
    for (int row = 0; row < marks.size(); ++row) {
        const QJsonObject sig = marks.at(row).toObject();
        table_->setItem(row, 0, new QTableWidgetItem(signal_label(sig.value("type").toString())));
        table_->setItem(row, 1, new QTableWidgetItem(QString::number(sig.value("index").toInt() + 1)));
        table_->setItem(row, 2, new QTableWidgetItem(QString::number(sig.value("price").toDouble(), 'f', 4)));
        table_->setItem(row, 3, new QTableWidgetItem(sig.value("reason").toString()));
    }
    status_->setText(QStringLiteral("%1  ·  笔 %2  ·  线段 %3  ·  中枢 %4  ·  信号 %5")
                         .arg(obj.value("summary").toString())
                         .arg(obj.value("bi").toArray().size())
                         .arg(obj.value("segments").toArray().size())
                         .arg(obj.value("zhongshu").toArray().size())
                         .arg(marks.size()));
}

void ChanlunScreen::run_sample() {
    set_busy(true);
    QPointer<ChanlunScreen> self(this);
    python::PythonRunner::RunOptions opts;
    opts.expect_json = true;
    opts.timeout_ms = 60000;
    python::PythonRunner::instance().run_with_options(
        QStringLiteral("chanlun/analyze.py"), {QStringLiteral("--sample")}, opts,
        [self](python::PythonResult result) {
            if (!self)
                return;
            const QString error = result.success ? QString() : result.error;
            self->apply_json(result.output, error.isEmpty() && !result.success ? QStringLiteral("缠论脚本没有返回结果")
                                                                               : error);
        });
}

void ChanlunScreen::run_csv() {
    const QString path = QFileDialog::getOpenFileName(this, QStringLiteral("打开 OHLC CSV"), QString(),
                                                      QStringLiteral("CSV (*.csv *.txt);;All files (*)"));
    if (path.isEmpty())
        return;
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text)) {
        status_->setText(QStringLiteral("打不开文件"));
        return;
    }
    QString error;
    const QJsonArray bars = bars_from_csv(QString::fromUtf8(file.readAll()), &error);
    if (!error.isEmpty()) {
        status_->setText(error);
        return;
    }
    QJsonObject payload;
    payload["bars"] = bars;
    set_busy(true);
    QPointer<ChanlunScreen> self(this);
    python::PythonRunner::RunOptions opts;
    opts.expect_json = true;
    opts.timeout_ms = 60000;
    opts.stdin_data = QJsonDocument(payload).toJson(QJsonDocument::Compact);
    python::PythonRunner::instance().run_with_options(
        QStringLiteral("chanlun/analyze.py"), {}, opts, [self](python::PythonResult result) {
            if (!self)
                return;
            self->apply_json(result.output, result.success ? QString() : result.error);
        });
}

} // namespace fincept::screens
