const path = require('path');

function createChunkName(moduleContext = '') {
  const moduleName = path.basename(moduleContext.replace(/\\/g, '/')) || 'common';
  return `chunk-${moduleName.replace(/[^a-zA-Z0-9._-]/g, '-')}`;
}

module.exports = { createChunkName };
