import 'mobile_api_client.dart';

/// Turns any failure of a server call into one sentence the user can act on.
/// Never includes tokens, addresses with credentials or response bodies.
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

/// Whether the failure means the server could not be reached at all, as
/// opposed to the server answering with an error.
bool isConnectivityFailure(Object error) => error is MobileNetworkException;
