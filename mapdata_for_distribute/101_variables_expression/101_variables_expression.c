// 101_variables_expression
int main(void) {
  int day = 3;               // 経過日数
  float base_temp = 15.0f;   // 基本気温(℃)
  float humidity = 0.65f;    // 湿度(0〜1)
  double pressure = 1013.25; // 気圧(hPa)
  char weather_code = 'S';   // S:晴れ, R:雨など

  float temp_variation = day * 1.2f;
  float temperature = base_temp + temp_variation - (humidity * 2.0f);

  pressure -= day * 1.8;   // 日数に応じて気圧低下
  humidity += 0.03f * day; // 湿度上昇
  humidity = (humidity > 1.0f) ? 1.0f : humidity;

  float dew_point = temperature - ((100.0f - humidity * 100.0f) / 5.0f);

  int storm_factor = (int)(humidity * 50) + (int)((1013.0 - pressure) * 0.2);

  weather_code = (storm_factor > 40) ? 'R' : 'S';

  return weather_code;
}
