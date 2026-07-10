module.exports = {
  testEnvironment: "jsdom",
  setupFilesAfterEnv: ["<rootDir>/src/setupTests.js"],
  moduleNameMapper: {
    "\\.(css|less|sass|scss)$": "<rootDir>/src/__mocks__/styleMock.js",
    "\\.(gif|jpg|jpeg|png|svg|ico)$": "<rootDir>/src/__mocks__/fileMock.js",
  },
  transform: {
    "^.+\\.[jt]sx?$": "babel-jest",
  },
};
