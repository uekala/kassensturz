import 'mobile_api_client.dart';

/// Macht aus jedem Fehler eines Serveraufrufs einen Satz, mit dem der Nutzer etwas anfangen kann.
/// Enthält nie Tokens, Adressen mit Zugangsdaten oder Antwortinhalte.
String describeMobileError(Object error) {
  if (error is MobileSessionExpiredException) {
    return 'Dieses Gerät ist nicht mehr angemeldet. '
        'Bitte kopple es in Kassensturz neu.';
  }
  if (error is MobileNetworkException) {
    switch (error.failure) {
      case MobileNetworkFailure.unreachable:
        return 'Der Server ist nicht erreichbar. '
            'Ist Tailscale auf diesem Gerät eingeschaltet?';
      case MobileNetworkFailure.timeout:
        return 'Der Server antwortet nicht rechtzeitig. '
            'Prüfe die Verbindung und versuche es erneut.';
      case MobileNetworkFailure.certificate:
        return 'Die sichere Verbindung konnte nicht geprüft werden. '
            'Prüfe die Serveradresse.';
      case MobileNetworkFailure.interrupted:
        return 'Die Verbindung wurde unterbrochen. Versuche es erneut.';
    }
  }
  if (error is MobileApiException) {
    switch (error.code) {
      case 'network_not_allowed':
        return 'Der Server lässt dieses Netz nicht zu. '
            'Verbinde dich über Tailscale.';
      case 'https_required':
        return 'Der Server verlangt eine HTTPS-Verbindung.';
      case 'rate_limited':
        return 'Zu viele Anfragen. Bitte warte einen Moment.';
      case 'account_not_manual':
      case 'not_editable':
      case 'not_deletable':
      case 'invalid_request':
      case 'pairing_rejected':
      case 'bank_refused':
        return error.message;
    }
    if (error.statusCode == 404 || error.statusCode == 405) {
      return 'Der Server kennt diese Funktion nicht. '
          'Bitte aktualisiere Kassensturz in Home Assistant.';
    }
    if (error.statusCode >= 500) {
      return 'Der Server meldet einen Fehler. Versuche es später erneut.';
    }
    return error.message;
  }
  if (error is FormatException) return error.message.toString();
  return 'Der Server konnte nicht erreicht werden. '
      'Prüfe Adresse und VPN-Verbindung.';
}

/// Ob der Fehler bedeutet, dass der Server gar nicht erreichbar war, im
/// Gegensatz zu einem Server, der mit einem Fehler antwortet.
bool isConnectivityFailure(Object error) => error is MobileNetworkException;
