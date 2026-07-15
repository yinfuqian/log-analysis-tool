const { createChunkName } = require('../build/chunkName');

describe('createChunkName', () => {
  test('extracts a safe chunk name from Windows module paths', () => {
    expect(createChunkName('E:\\project\\node_modules\\axios')).toBe('chunk-axios');
  });

  test('extracts a safe chunk name from POSIX module paths', () => {
    expect(createChunkName('/project/node_modules/axios')).toBe('chunk-axios');
  });
});
