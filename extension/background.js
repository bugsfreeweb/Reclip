chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: 'sendToReclip',
    title: 'Send to ReClip',
    contexts: ['page', 'link', 'video', 'audio'],
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  const url = info.linkUrl || info.pageUrl || tab.url;
  if (!url || !url.startsWith('http')) return;
  try {
    const serverUrl = await chrome.storage.local.get('reclipServer').then(r => r.reclipServer || 'http://localhost:8899');
    await fetch(serverUrl + '/api/history', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, title: tab.title || '', thumbnail: '' }),
    });
  } catch (err) {
    console.error('ReClip: Failed to send URL', err);
  }
});
