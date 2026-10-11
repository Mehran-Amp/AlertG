import 'dart:convert';
import 'package:http/http.dart' as http;

/// Utility class for safe HTTP response decoding with robust UTF-8 support.
///
/// Dart's default `response.body` falls back to ISO-8859-1 (Latin-1) whenever
/// the response header is `Content-Type: application/json` without an explicit
/// `charset=utf-8` parameter. This class decodes raw `response.bodyBytes`
/// using UTF-8 to prevent any character corruption (e.g. Persian/Farsi text).
class HttpUtils {
  /// Safely decodes HTTP response body bytes as UTF-8 and parses as JSON.
  static dynamic decodeJson(http.Response response) {
    return jsonDecode(utf8.decode(response.bodyBytes));
  }

  /// Safely decodes HTTP response body bytes as a UTF-8 string.
  static String decodeUtf8(http.Response response) {
    return utf8.decode(response.bodyBytes);
  }
}

/// Standalone top-level function for concise JSON decoding
dynamic safeJsonDecode(http.Response response) => HttpUtils.decodeJson(response);

/// Standalone top-level function for raw UTF-8 string decoding
String safeUtf8Decode(http.Response response) => HttpUtils.decodeUtf8(response);
