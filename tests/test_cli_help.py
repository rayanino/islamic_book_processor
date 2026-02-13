from ibp.cli import build_parser


def test_cli_help_lists_subcommands(capsys):
    parser = build_parser()
    try:
        parser.parse_args(["--help"])
    except SystemExit:
        pass

    output = capsys.readouterr().out
    assert "scan" in output
    assert "propose" in output
    assert "approve" in output
