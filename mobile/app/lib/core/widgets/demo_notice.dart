import 'package:flutter/material.dart';

import '../design/app_theme.dart';

class DemoNotice extends StatelessWidget {
  const DemoNotice({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.fromLTRB(20, 8, 20, 4),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
      decoration: BoxDecoration(
        color: AppTheme.softBrand,
        borderRadius: BorderRadius.circular(9),
      ),
      child: const Row(
        children: [
          Icon(Icons.info_outline_rounded, size: 16, color: AppTheme.brand),
          SizedBox(width: 9),
          Expanded(
            child: Text(
              'Beispieldaten – noch nicht mit deinem Server verbunden',
              style: TextStyle(
                color: AppTheme.brand,
                fontSize: 11,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
