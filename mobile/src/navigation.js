// Базовая структура мобильного приложения покупателя (Этап 4)
// Фрейм: React Native / Expo или обычный WebView для PWA/APK

export const SCREENS = {
  HOME: 'Home',
  CATALOG: 'Catalog',
  PRODUCT: 'Product',
  CART: 'Cart',
  ORDERS: 'Orders',
  PROFILE: 'Profile',
  SEARCH_GEO: 'SearchGeo',
};

export const NAVIGATION = [
  { screen: SCREENS.HOME, label: 'Главная', icon: '🏠' },
  { screen: SCREENS.CATALOG, label: 'Каталог', icon: '📂' },
  { screen: SCREENS.CART, label: 'Корзина', icon: '🛒' },
  { screen: SCREENS.ORDERS, label: 'Заказы', icon: '📦' },
];
