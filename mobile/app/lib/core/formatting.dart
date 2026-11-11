String formatEuro(double value) {
  final parts = value.abs().toStringAsFixed(2).split('.');
  final whole = parts[0].replaceAllMapped(
    RegExp(r'\B(?=(\d{3})+(?!\d))'),
    (_) => '.',
  );
  final sign = value < 0 ? '−' : '';
  return '$sign$whole,${parts[1]} €';
}

String formatSignedEuro(double value) {
  final sign = value < 0 ? '−' : '+';
  return '$sign${formatEuro(value.abs())}';
}

String formatDate(DateTime date) {
  final day = date.day.toString().padLeft(2, '0');
  final month = date.month.toString().padLeft(2, '0');
  return '$day.$month.${date.year}';
}
