import test from 'node:test';
import assert from 'node:assert/strict';
import { remarkHighlight } from '../src/lib/remark-highlight.ts';

test('remarkHighlight escapes highlighted text before emitting mark HTML', () => {
  const tree: any = {
    type: 'root',
    children: [
      {
        type: 'paragraph',
        children: [
          {
            type: 'text',
            value: 'before ==<img src=x onerror=alert(1)> & "quote"== after',
          },
        ],
      },
    ],
  };

  remarkHighlight()(tree);

  const children = tree.children[0].children;
  assert.equal(children[1].type, 'html');
  assert.equal(
    children[1].value,
    '<mark>&lt;img src=x onerror=alert(1)&gt; &amp; &quot;quote&quot;</mark>'
  );
});
