export default {
  multipass: true,
  plugins: [
    {
      name: "preset-default",
      params: {
        overrides: {
          mergePaths: false,
        },
      },
    },
    {
      name: "cleanupNumericValues",
      params: { floatPrecision: 1 },
    },
    "convertStyleToAttrs",
    "collapseGroups",
  ],
};
