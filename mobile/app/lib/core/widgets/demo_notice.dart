import 'package:flutter/material.dart';

class DemoNotice extends StatelessWidget {
  const DemoNotice({super.key});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.fromLTRB(16, 8, 16, 4),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF8E9),
        border: Border.all(color: const Color(0xFFF4E3BD)),
        borderRadius: BorderRadius.circular(12),
      ),
      child: const Row(
        children: [
          Icon(Icons.info_outline_rounded, size: 17, color: Color(0xFF865B12)),
          SizedBox(width: 9),
          Expanded(
            child: Text(
              'Beispieldaten – noch nicht mit deinem Server verbunden',
              style: TextStyle(
                color: Color(0xFF765319),
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
