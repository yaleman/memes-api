export function filterImages(images, search) {
  return images.filter(image => {
    const searchTerm = search.toLowerCase();
    if (searchTerm === '') {
      return true;
    }
    const image_lower = image.toString().toLowerCase();
    let foundit = true;
    searchTerm.split(" ").forEach(term => {
      if (image_lower.includes(term) === false) {
        foundit = false;
      }
    });
    return foundit;
  });
}

export function paginate(images, currentPage, perPage) {
  let start = (currentPage - 1) * perPage;
  let end = (currentPage - 1) * perPage + perPage;
  return images.slice(start, end);
}

export function buildSearchParams(search, currentPage) {
  let qp = new URLSearchParams();
  if (search !== '') {
    qp.set('q', search);
  } else {
    qp.set("q", "");
  }
  if (currentPage > 0) {
    qp.set('p', currentPage);
  } else {
    qp.set("p", "");
  }
  return qp;
}

export function parseSearchParams(urlSearchParams) {
  let search = '';
  let page = 1;

  const q = urlSearchParams.get("q");
  if (q != "" && q != null) {
    search = q;
  }

  const p = urlSearchParams.get("p");
  if (p != "" && p != null) {
    page = Number(p);
  }

  return { search, page };
}
