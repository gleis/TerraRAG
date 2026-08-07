import "./styles.css";

export const metadata = {
  title: "TerraRAG — Local infrastructure intelligence",
  description: "Private, source-grounded Terraform and Terragrunt analysis.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
