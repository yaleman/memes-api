import { describe, it, expect } from 'vitest';
import { filterImages, paginate, buildSearchParams, parseSearchParams } from '@js/memesapi-utils.js';

describe('filterImages', () => {
  const images = [
    'cat-meme.jpg',
    'dog-photo.png',
    'cat-and-dog.gif',
    'funny-cat.bmp',
    'landscape.jpg',
  ];

  it('returns all images when search is empty', () => {
    expect(filterImages(images, '')).toEqual(images);
  });

  it('filters by single term (case insensitive)', () => {
    expect(filterImages(images, 'cat')).toEqual([
      'cat-meme.jpg',
      'cat-and-dog.gif',
      'funny-cat.bmp',
    ]);
  });

  it('filters by multiple space-separated terms (AND logic)', () => {
    expect(filterImages(images, 'cat dog')).toEqual([
      'cat-and-dog.gif',
    ]);
  });

  it('returns no matches for non-existent term', () => {
    expect(filterImages(images, 'zebra')).toEqual([]);
  });

  it('handles uppercase search terms', () => {
    expect(filterImages(images, 'CAT')).toEqual([
      'cat-meme.jpg',
      'cat-and-dog.gif',
      'funny-cat.bmp',
    ]);
  });

  it('handles mixed case filenames', () => {
    const mixed = ['Cat-Meme.JPG', 'DOG-photo.PNG'];
    expect(filterImages(mixed, 'cat')).toEqual(['Cat-Meme.JPG']);
  });
});

describe('paginate', () => {
  const images = Array.from({ length: 35 }, (_, i) => `img${i}.jpg`);

  it('returns first page correctly', () => {
    expect(paginate(images, 1, 15)).toEqual(images.slice(0, 15));
  });

  it('returns second page correctly', () => {
    expect(paginate(images, 2, 15)).toEqual(images.slice(15, 30));
  });

  it('returns remaining items on last page', () => {
    expect(paginate(images, 3, 15)).toEqual(images.slice(30, 35));
  });

  it('returns empty for page beyond total', () => {
    expect(paginate(images, 100, 15)).toEqual([]);
  });

  it('handles empty array', () => {
    expect(paginate([], 1, 15)).toEqual([]);
  });

  it('handles page size larger than array', () => {
    const small = ['a.jpg', 'b.jpg'];
    expect(paginate(small, 1, 15)).toEqual(small);
  });

  it('calculates correct page count', () => {
    expect(Math.ceil(35 / 15)).toBe(3);
    expect(Math.ceil(30 / 15)).toBe(2);
    expect(Math.ceil(1 / 15)).toBe(1);
  });
});

describe('buildSearchParams', () => {
  it('includes both query and page when set', () => {
    const params = buildSearchParams('cat', 2);
    expect(params.get('q')).toBe('cat');
    expect(params.get('p')).toBe('2');
  });

  it('sets q to empty string when search is empty', () => {
    const params = buildSearchParams('', 1);
    expect(params.get('q')).toBe('');
  });

  it('sets p to empty string when page is 0 or negative', () => {
    const params = buildSearchParams('cat', 0);
    expect(params.get('p')).toBe('');
  });
});

describe('parseSearchParams', () => {
  it('parses query and page from URLSearchParams', () => {
    const qp = new URLSearchParams('q=cat&p=2');
    expect(parseSearchParams(qp)).toEqual({ search: 'cat', page: 2 });
  });

  it('defaults page to 1 when missing', () => {
    const qp = new URLSearchParams('q=cat');
    expect(parseSearchParams(qp)).toEqual({ search: 'cat', page: 1 });
  });

  it('defaults search to empty when missing', () => {
    const qp = new URLSearchParams('p=3');
    expect(parseSearchParams(qp)).toEqual({ search: '', page: 3 });
  });

  it('defaults both when URLSearchParams is empty', () => {
    const qp = new URLSearchParams();
    expect(parseSearchParams(qp)).toEqual({ search: '', page: 1 });
  });

  it('handles null values gracefully', () => {
    const qp = new URLSearchParams();
    qp.set('q', '');
    qp.set('p', '');
    expect(parseSearchParams(qp)).toEqual({ search: '', page: 1 });
  });
});
