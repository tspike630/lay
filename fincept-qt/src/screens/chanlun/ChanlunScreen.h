#pragma once

#include <QWidget>

class QLabel;
class QPushButton;
class QTableWidget;

namespace fincept::screens {

class ChanlunChart;

/// 缠论 screen: fractals, bi, segments, zhongshu, and three buy/sell points.
/// Calculation is local Python. bbfamily/abu ships no chanlun source.
class ChanlunScreen : public QWidget {
    Q_OBJECT
  public:
    explicit ChanlunScreen(QWidget* parent = nullptr);

  private:
    void run_sample();
    void run_csv();
    void apply_json(const QString& json_text, const QString& error);
    void set_busy(bool busy);

    ChanlunChart* chart_ = nullptr;
    QTableWidget* table_ = nullptr;
    QLabel* status_ = nullptr;
    QLabel* note_ = nullptr;
    QPushButton* sample_btn_ = nullptr;
    QPushButton* csv_btn_ = nullptr;
};

} // namespace fincept::screens
