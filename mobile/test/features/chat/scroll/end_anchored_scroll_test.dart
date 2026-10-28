import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:karmi_app/features/chat/scroll/end_anchored_scroll.dart';

void main() {
  group('EndAnchoredScroll', () {
    testWidgets(
      'pinned: a ListView with items growing each step while controller pinned: '
      'after adding items and pumping, maxScrollExtent is at position '
      '(pixels == maxScrollExtent within 1px) and isAtBottom true',
      (tester) async {
        final controller = EndAnchoredScrollController();
        final items = ValueNotifier<List<int>>([0, 1, 2, 3, 4]);

        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: SizedBox(
                height: 300,
                child: EndAnchoredScroll(
                  controller: controller,
                  builder: (context, scrollController, physics) {
                    return ValueListenableBuilder<List<int>>(
                      valueListenable: items,
                      builder: (context, list, _) {
                        return ListView(
                          controller: scrollController,
                          physics: physics,
                          scrollCacheExtent: const ScrollCacheExtent.pixels(
                            5000,
                          ),
                          children: [
                            for (final i in list)
                              SizedBox(height: 100, child: Text('Item $i')),
                          ],
                        );
                      },
                    );
                  },
                ),
              ),
            ),
          ),
        );
        await tester.pump();

        expect(
          (controller.scrollController.position.pixels -
                  controller.scrollController.position.maxScrollExtent)
              .abs(),
          lessThanOrEqualTo(1.0),
        );
        expect(controller.isAtBottom.value, isTrue);

        // Step 1: grow items
        items.value = [0, 1, 2, 3, 4, 5, 6, 7];
        await tester.pump();

        expect(
          (controller.scrollController.position.pixels -
                  controller.scrollController.position.maxScrollExtent)
              .abs(),
          lessThanOrEqualTo(1.0),
        );
        expect(controller.isAtBottom.value, isTrue);

        // Step 2: grow items again
        items.value = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
        await tester.pump();

        expect(
          (controller.scrollController.position.pixels -
                  controller.scrollController.position.maxScrollExtent)
              .abs(),
          lessThanOrEqualTo(1.0),
        );
        expect(controller.isAtBottom.value, isTrue);
      },
    );

    testWidgets('not pinned: user scrolls to top (jumpTo(0)), content grows; '
        'pixels stays 0 and hasNewContent true and isAtBottom false', (
      tester,
    ) async {
      final controller = EndAnchoredScrollController();
      final items = ValueNotifier<List<int>>([0, 1, 2, 3, 4, 5, 6, 7]);

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SizedBox(
              height: 300,
              child: EndAnchoredScroll(
                controller: controller,
                builder: (context, scrollController, physics) {
                  return ValueListenableBuilder<List<int>>(
                    valueListenable: items,
                    builder: (context, list, _) {
                      return ListView(
                        controller: scrollController,
                        physics: physics,
                        scrollCacheExtent: const ScrollCacheExtent.pixels(5000),
                        children: [
                          for (final i in list)
                            SizedBox(height: 100, child: Text('Item $i')),
                        ],
                      );
                    },
                  );
                },
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      // User scrolls to top
      controller.scrollController.jumpTo(0);
      await tester.pump();

      expect(controller.scrollController.position.pixels, 0.0);
      expect(controller.isAtBottom.value, isFalse);
      expect(controller.hasNewContent.value, isFalse);

      // Content grows while scrolled up
      items.value = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];
      await tester.pump();

      expect(controller.scrollController.position.pixels, 0.0);
      expect(controller.hasNewContent.value, isTrue);
      expect(controller.isAtBottom.value, isFalse);
    });

    testWidgets(
      'jumpToLatest() from top lands at bottom and clears hasNewContent after pumpAndSettle',
      (tester) async {
        final controller = EndAnchoredScrollController();
        final items = ValueNotifier<List<int>>([0, 1, 2, 3, 4, 5, 6, 7]);

        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: SizedBox(
                height: 300,
                child: EndAnchoredScroll(
                  controller: controller,
                  builder: (context, scrollController, physics) {
                    return ValueListenableBuilder<List<int>>(
                      valueListenable: items,
                      builder: (context, list, _) {
                        return ListView(
                          controller: scrollController,
                          physics: physics,
                          scrollCacheExtent: const ScrollCacheExtent.pixels(
                            5000,
                          ),
                          children: [
                            for (final i in list)
                              SizedBox(height: 100, child: Text('Item $i')),
                          ],
                        );
                      },
                    );
                  },
                ),
              ),
            ),
          ),
        );
        await tester.pump();

        // Scroll to top
        controller.scrollController.jumpTo(0);
        await tester.pump();

        // Grow content
        items.value = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
        await tester.pump();

        expect(controller.hasNewContent.value, isTrue);
        expect(controller.isAtBottom.value, isFalse);

        // Jump to latest
        controller.jumpToLatest();
        await tester.pumpAndSettle();

        expect(
          (controller.scrollController.position.pixels -
                  controller.scrollController.position.maxScrollExtent)
              .abs(),
          lessThanOrEqualTo(1.0),
        );
        expect(controller.isAtBottom.value, isTrue);
        expect(controller.hasNewContent.value, isFalse);
      },
    );

    testWidgets(
      'user scrolling back into threshold re-pins and clears hasNewContent',
      (tester) async {
        final controller = EndAnchoredScrollController();
        final items = ValueNotifier<List<int>>([0, 1, 2, 3, 4, 5, 6, 7]);

        await tester.pumpWidget(
          MaterialApp(
            home: Scaffold(
              body: SizedBox(
                height: 300,
                child: EndAnchoredScroll(
                  controller: controller,
                  builder: (context, scrollController, physics) {
                    return ValueListenableBuilder<List<int>>(
                      valueListenable: items,
                      builder: (context, list, _) {
                        return ListView(
                          controller: scrollController,
                          physics: physics,
                          scrollCacheExtent: const ScrollCacheExtent.pixels(
                            5000,
                          ),
                          children: [
                            for (final i in list)
                              SizedBox(height: 100, child: Text('Item $i')),
                          ],
                        );
                      },
                    );
                  },
                ),
              ),
            ),
          ),
        );
        await tester.pump();

        controller.scrollController.jumpTo(0);
        await tester.pump();

        items.value = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9];
        await tester.pump();

        expect(controller.hasNewContent.value, isTrue);

        // Scroll near bottom (within threshold of 48px)
        final max = controller.scrollController.position.maxScrollExtent;
        controller.scrollController.jumpTo(max - 20);
        await tester.pump();

        expect(controller.isAtBottom.value, isTrue);
        expect(controller.hasNewContent.value, isFalse);
      },
    );

    testWidgets('jumpToLatest under reduced motion jumps immediately', (
      tester,
    ) async {
      final controller = EndAnchoredScrollController();

      await tester.pumpWidget(
        MaterialApp(
          home: MediaQuery(
            data: const MediaQueryData(disableAnimations: true),
            child: Scaffold(
              body: SizedBox(
                height: 300,
                child: EndAnchoredScroll(
                  controller: controller,
                  builder: (context, scrollController, physics) {
                    return ListView(
                      controller: scrollController,
                      physics: physics,
                      scrollCacheExtent: const ScrollCacheExtent.pixels(5000),
                      children: [
                        for (int i = 0; i < 20; i++)
                          SizedBox(height: 100, child: Text('Item $i')),
                      ],
                    );
                  },
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      controller.scrollController.jumpTo(0);
      await tester.pump();
      expect(controller.scrollController.position.pixels, 0.0);

      controller.jumpToLatest();
      await tester.pump();
      expect(
        controller.scrollController.position.pixels,
        controller.scrollController.position.maxScrollExtent,
      );
      expect(controller.isAtBottom.value, isTrue);
    });
  });
}
