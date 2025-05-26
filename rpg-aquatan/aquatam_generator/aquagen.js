const tmplColors = {
  背景: [190, 179, 145],
  帽子1: [6, 72, 39],
  帽子2: [19, 84, 49],
  帽子3: [24, 97, 61],
  帽子4: [0, 126, 64],
  帽子5: [18, 177, 108],
  目1: [30, 142, 247],
  目2: [94, 206, 247],
  頬口手1: [0, 0, 255],
  頬口手2: [0, 255, 0],
  腹1: [231, 70, 14],
  腹2: [247, 86, 30],
  腹3: [255, 0, 0],
  腹4: [255, 134, 78],
  足1: [110, 78, 46],
  足2: [142, 110, 78],
  胴体1: [39, 42, 45],
  胴体2: [55, 58, 61],
  胴体3: [71, 74, 77],
  胴体4: [87, 90, 93],
  胴体5: [89, 98, 100],
  胴体6: [103, 106, 109],
};

const defaultColors = {
  背景: [190, 179, 145, 255],
  帽子1: [6, 72, 39, 255],
  帽子2: [19, 84, 49, 255],
  帽子3: [24, 97, 61, 255],
  帽子4: [0, 126, 64, 255],
  帽子5: [18, 177, 108, 255],
  目1: [30, 142, 247, 255],
  目2: [94, 206, 247, 255],
  頬口手1: [247, 86, 30, 255],
  頬口手2: [255, 134, 78, 255],
  腹1: [231, 70, 14, 255],
  腹2: [247, 86, 30, 255],
  腹3: [255, 118, 62, 255],
  腹4: [255, 134, 78, 255],
  足1: [110, 78, 46, 255],
  足2: [142, 110, 78, 255],
  胴体1: [39, 42, 45, 255],
  胴体2: [55, 58, 61, 255],
  胴体3: [71, 74, 77, 255],
  胴体4: [87, 90, 93, 255],
  胴体5: [89, 98, 100, 255],
  胴体6: [103, 106, 109, 255],
};

const transparentColor = [255, 255, 255, 0];

let aquaTmplImage;

function toRgb(arr) {
  return (
    '#' +
    arr
      .slice(0, 3)
      .map((item) => ('00' + item.toString(16)).slice(-2))
      .join('')
  ); // 透明度はinputが受け付けない
}

function fromRgb(str) {
  str = str.replace(/#/, '');
  if (str.length !== 6) throw new Error('invalid value');

  return [
    parseInt(str.slice(0, 2), 16),
    parseInt(str.slice(2, 4), 16),
    parseInt(str.slice(4, 6), 16),
    255, // inputが透明度寄越さないのでデフォ
  ];
}

function toHex(arr) {
  return (arr[0] << 16) | (arr[1] << 8) | arr[2];
}

function getNewColorMap() {
  const colors = {};
  $('#inputform input[type="color"]').each((_, elem) => {
    elem = $(elem);
    colors[elem.attr('name')] = fromRgb(elem.val());
  });

  return colors;
}

function updateAquatan() {
  const canvas = document.querySelector('#output').getContext('2d');
  canvas.drawImage(aquaTmplImage, 0, 0);

  const image = canvas.getImageData(0, 0, 128, 128);
  const colors = getNewColorMap();
  const bgTrans = $('#bg_trans').prop('checked');

  const replacementTable = new Map();
  for (const itemName of Object.keys(tmplColors)) {
    const key = toHex(tmplColors[itemName]);

    if (itemName === '背景' && bgTrans) {
      replacementTable.set(key, transparentColor);
    } else {
      replacementTable.set(key, colors[itemName] || tmplColors[itemName]);
    }
  }

  for (let i = 0; i < image.data.length; i += 4) {
    const key = toHex(image.data.slice(i, i + 3));
    if (replacementTable.has(key)) {
      const rep = replacementTable.get(key);
      image.data[i] = rep[0];
      image.data[i + 1] = rep[1];
      image.data[i + 2] = rep[2];
      image.data[i + 3] = rep[3];
    }
  }

  canvas.putImageData(image, 0, 0);

  console.log('done');
}

let previewCount = 0;
let previewPose = 0;

function updatePreviewFrame() {
  const previewElem = document.querySelector('#preview');
  const outputElem = document.querySelector('#output');
  const previewCtx = previewElem.getContext('2d');
  previewCount++;
  if (previewCount == 4) previewCount = 0;

  previewCtx.clearRect(0, 0, 32, 32);
  previewCtx.drawImage(
    outputElem,
    previewCount * 32,
    previewPose * 32,
    32,
    32,
    0,
    0,
    32,
    32
  );
}

function createGifAndDownload() {
  const outputElem = document.querySelector('#output');
  const delay = $('#preview_interval').val();
  const zoom = $('#gif_zoom').val();

  const gif = new GIF({
    quality: 4,
    width: 32 * zoom,
    height: 32 * zoom,
    globalPalette: true,
  });
  const gifCanvas = document.createElement('canvas');
  gifCanvas.width = 32 * zoom;
  gifCanvas.height = 32 * zoom;
  gifCanvas.style.imageRendering = 'pixelated';
  const ctx = gifCanvas.getContext('2d');
  ctx.imageSmoothingEnabled = false;

  for (let i = 0; i < 4; i++) {
    ctx.clearRect(0, 0, 32 * zoom, 32 * zoom);
    ctx.drawImage(
      outputElem,
      i * 32,
      previewPose * 32,
      32,
      32,
      0,
      0,
      32 * zoom,
      32 * zoom
    );
    gif.addFrame(ctx, { copy: true, delay });
  }

  gif.on('finished', (blob) => {
    const link = document.createElement('a');
    link.download = 'aquatan.gif';
    link.href = URL.createObjectURL(blob);

    link.click();
  });
  gif.render();
}

$(document).ready(() => {
  const inputForm = $('#inputform');
  for (const itemName of Object.keys(tmplColors)) {
    $('<div>')
      .append($('<label>').text(itemName))
      .append(
        $('<input>')
          .attr({
            name: itemName,
            type: 'color',
            default: toRgb(defaultColors[itemName]),
            value: toRgb(defaultColors[itemName] || tmplColors[itemName]),
          })
          .on('change', () => updateAquatan())
      )
      .appendTo(inputForm);
  }

  $('#bg_trans').on('change', () => updateAquatan());
  $('form').on('reset', () => {
    setTimeout(() => updateAquatan(), 10); // TODO: こういう実装嫌いなんだが
  });

  $('#download').click(() => {
    const outputElem = document.querySelector('#output');

    const link = document.createElement('a');
    link.download = 'aquatan.png';
    link.href = outputElem.toDataURL('image/png');

    link.click();
  });

  $('#gif_download').click(() => {
    createGifAndDownload();
  });

  aquaTmplImage = document.createElement('img');
  aquaTmplImage.addEventListener('load', () => updateAquatan());
  aquaTmplImage.src = '15000.png';

  const previewElem = document.querySelector('#preview');

  let timer = setInterval(updatePreviewFrame, 250);
  $('#preview_interval').on('change', () => {
    clearInterval(timer);
    timer = setInterval(updatePreviewFrame, $('#preview_interval').val());
  });

  previewElem.addEventListener('click', () => {
    previewPose++;
    if (previewPose == 4) previewPose = 0;
  });
});
